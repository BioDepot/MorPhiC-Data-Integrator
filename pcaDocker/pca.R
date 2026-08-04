# Load libraries
library(tidyverse)
library(ggrepel)
library(DESeq2)
library(readxl)
library(tibble)
library(locfit)
library(gplots)
library(pheatmap)
library(SRAdb)
library(jsonlite)
library(EnhancedVolcano)

options(error = function() {
    traceback(2)
    quit(status = 1)
})


args <- commandArgs(trailingOnly = TRUE)

mdataJson <- Sys.getenv("metadata_json")
counts_dir <- Sys.getenv("counts_dir")
geneTable <- paste0(counts_dir, "/genesCounts.csv")
# Read in dashboard metadata groupings json (nested list, extract $groups first)
dashboard_metadata <- fromJSON(mdataJson)$groups

# First column: name, second column: samples (nested list containing "srr_id" and "layout")
# Separate srr_id and layout into separate columns
dashboard_metadata <- dashboard_metadata %>%
    mutate(samples = map(samples, ~ tibble(srr_id = .x$srr_id, layout = .x$layout))) %>%
    unnest(samples) %>%
    # Remove "layout" column, not needed for analysis
    dplyr::select(-layout)

dashboard_metadata

# Read in genesCounts.csv (set first column (gene names 'Name') as row names)
genes_counts <- read_delim(geneTable,delim = "\t", col_names = TRUE) %>%
    column_to_rownames(var = "Name")

head(genes_counts)

# Column names of genes_counts should match srr_id in dashboard_metadata,
# gene_counts names may have something appended to them, so we need to match
# the srr_id to the column names of genes_counts
# (excluding first column's gene `Name`), and remove any appended text
# (e.g. ".1", ".2", "_trimmed", etc.)
# genes_counts <- genes_counts %>%
    # rename_with(~ str_remove(., "\\..*|_trimmed$"), -`Name`) %>%
    # rename_with(~ str_remove(., "_R1$|_R2$"), -`Name`)
    # rename_with(~ str_remove(., "\\..*|_trimmed$")) %>%
    # rename_with(~ str_remove(., "_R1$|_R2$"))

# Column names of genes_counts should match srr_id in dashboard_metadata,
# remove any appended text from the column names of genes_counts
# past "_" (e.g. "<name>_trimmed", "<name>_R1", "<name>_R2", "<name>_val_1", "<name>_val_2", or the same types but "." instead of "_", to "<name>")
genes_counts <- genes_counts %>%
    rename_with(~ str_remove(., "_trimmed$|_R1$|_R2$|_val_1$|_val_2$|\\..*"), everything())


head(genes_counts)

# Omit any samples in dashboard_metadata that are not in genes_counts
dashboard_metadata <- dashboard_metadata %>%
    filter(srr_id %in% colnames(genes_counts))

print("SRR IDs not included in genes_counts:")
print(setdiff(dashboard_metadata$srr_id, colnames(genes_counts)))

### Format dashboard_metadata for DESeq2
# Create a DESeq2 compatible metadata dataframe
# (srr_id as row names, condition as factor)
metadata_df <- dashboard_metadata %>%
    dplyr::select(srr_id, name) %>%
    dplyr::mutate(condition = as.factor(name)) %>%
    column_to_rownames(var = "srr_id") %>%
    dplyr::select(-name)

metadata_df

# Final checks: ensure all srr_ids in metadata_df are in genes_counts
if (!all(rownames(metadata_df) %in% colnames(genes_counts))) {
    stop("Some srr_ids in metadata_df are not in genes_counts.")
}

# Ensure the ordering of srr_ids in metadata_df matches column names in genes_counts
if (all(rownames(metadata_df) == colnames(genes_counts))) {
    print("All srr_ids in metadata_df match column names in genes_counts.")
} else {
    print("Mismatch ordering between srr_ids in metadata_df and column names in genes_counts.")
    print("Matching srr_ids to genes_counts column names...")
    genes_counts <- genes_counts[, rownames(metadata_df)]
}

# Perform DESeq2 analysis
dds <- DESeqDataSetFromMatrix(countData = genes_counts,
                              colData = metadata_df,
                              design = ~ condition)
dds

# Run DESeq2 analysis
# This will perform normalization and statistical testing
dds <- DESeq(dds)
dds

# Set the alpha level for significance
alpha <- 0.05

# Extract results
res <- results(dds, alpha = alpha)
res
summary(res)

# Number of DEGs
num_degs <- sum(res$padj < alpha, na.rm = TRUE)
cat("Number of differentially expressed genes (DEGs) padj < 0.05: ", num_degs, "\n")
print(paste("Total number of genes:", nrow(res)))
print(paste("Total number of genes with non-NA padj:", sum(!is.na(res$padj))))

# Make a dataframe of results
res_df <- as.data.frame(res)

head(res_df)

# Replace Ensembl IDs with gene symbols using the local ensembl_gene_mapping.csv
# lookup table instead of querying the Ensembl biomaRt API, which has proven
# to be an unreliable single point of failure (transient 500s, network flakiness).
# ensembl_gene_mapping.csv IDs are versioned (e.g. "ENSG00000290825.1"), so the
# version suffix is stripped before matching against res_df's unversioned IDs.
gene_mapping <- read_csv("/app/ensembl_gene_mapping.csv", col_names = TRUE, show_col_types = FALSE) %>%
    mutate(ensembl_gene_id = str_remove(ensembl_gene_id, "\\..*")) %>%
    distinct(ensembl_gene_id, .keep_all = TRUE)

gene_symbols <- gene_mapping %>%
    filter(ensembl_gene_id %in% rownames(res_df)) %>%
    dplyr::rename(external_gene_name = gene_symbol)
head(gene_symbols)
nrow(gene_symbols)

# Merge gene symbols with results
res_df <- res_df %>%
    rownames_to_column(var = "ensembl_gene_id") %>%
    left_join(gene_symbols, by = "ensembl_gene_id") %>%
    # Some gene symbols may be empty, so use ensembl_gene_id as fallback
    mutate(gene_symbol = ifelse(is.na(external_gene_name) | external_gene_name == "", ensembl_gene_id, external_gene_name)) %>%
    # Set rownames to ensembl_gene_id again
    column_to_rownames(var = "ensembl_gene_id")

# For some reason column'external_gene_name' cannot be accessed directly,
# need to remove it at column 7
res_df <- res_df[, -7]

# Modify res_df to convert row names to a column (Ensomble_IDs), and column gene_symbol be the second column
res_df_csv <- res_df %>%
    rownames_to_column(var = "Ensembl_IDs") %>%
    dplyr::select(Ensembl_IDs, gene_symbol, everything())

head(res_df_csv)

# # Write results to CSV
# write_csv(res_df_csv, paste0(counts_dir, "/DESeq2_results.csv"))

### Create a volcano plot using EnhancedVolcano

# Change the f-cutoff value here (default is 2)
f_cutoff <- 2

EnhancedVolcano(res_df,
                lab = res_df$gene_symbol,
                x = 'log2FoldChange',
                y = 'padj',
                pCutoff = alpha,
                # FCcutoff = 1,
                title = "Volcano Plot of DEGs (padj)",
                subtitle = paste("Total DEGs:", num_degs))
                # pointSize = 3.0,
                # labSize = 3.0,
                # drawConnectors = TRUE,
                # widthConnectors = 0.5,
                # colAlpha = 0.5,
                # legendPosition = "right",
                # legendLabSize = 10,
                # legendIconSize = 3.0)


# Select top 20 DEGs based on padj
top_degs <- res_df %>%
    filter(!is.na(padj) & padj < alpha) %>%
    arrange(padj) %>%
    head(20)  # Change this number to select more/less DEGs
head(top_degs)


### Create a heatmap of the top DEGs
# Save the plot as a PNG file
png(file.path(counts_dir, "heatmap.png"), width = 800, height = 600)
heatmap.2(as.matrix(genes_counts[rownames(genes_counts) %in% rownames(top_degs), ]),
          scale = "row",
          main = "Heatmap of Top DEGs",
          labRow = top_degs$gene_symbol,
          labCol = rownames(metadata_df),
          margins = c(10, 10),
          col = bluered(100))

make_volcano_plot <- function(res,
                              gene_symbol,
                              ensembl_gene_id,
                              # gene_name,
                              d_group = "Volcano Plot of DEGs",
                              # ko1,
                              fc0 = 0.5,
                              p0  = 0.05,
                              clip_fc = 3,
                              volcano_figure_dir = NULL,
                              save_plot = FALSE) {
  # Subset columns for this KO/condition and clean column names
  # res_k <- res[, c(1, grep(ko1, names(res)))]
  res_k <- res
  # names(res_k) <- gsub(paste0(gene_name, "_", ko1, "_"), "", names(res_k))
  # names(res_k) <- gsub(paste0(gene_symbol, "_", ko1, "_"), "", names(res_k))

  # Define DE status
  ww_up   <- which((res_k$log2FoldChange >  fc0) & (res_k$padj < p0))
  ww_down <- which((res_k$log2FoldChange < -fc0) & (res_k$padj < p0))

  res_k$DE <- "No"
  res_k$DE[ww_up]   <- "Up"
  res_k$DE[ww_down] <- "Down"

  # Clip log2FC values to keep the plot compact
  res_k$log2FoldChange[res_k$log2FoldChange >  clip_fc] <-  clip_fc
  res_k$log2FoldChange[res_k$log2FoldChange < -clip_fc] <- -clip_fc

  # Colors for DE status
  col2use <- c("blue", "grey", "red")
  names(col2use) <- c("Down", "No", "Up")

  # Add gene symbols and labels for DE genes
  res_k$delabel <- NA
  # res_k$gene_symbol <- gene_symbol[
  #   match(res_k$gene_ID, ensembl_gene_id)
  # ]
  w_de <- which(res_k$DE != "No")
  res_k$delabel[w_de] <- res_k$gene_symbol[w_de]

  # Title group formatting
  # if (gene_symbol == "EPAS1") {
  #   d_group_in_title <- d_group
  # } else {
  #   d_group_in_title <- gsub("_nor", "", d_group)
  # }
  d_group_in_title <- d_group

  # message("DE counts for ", gene_symbol, " / ", ko1, ":")
  print(table(res_k$DE))

  # Build the volcano plot
  g <- ggplot(res_k, aes(x = log2FoldChange,
                         y = -log10(padj),
                         col = DE,
                         label = delabel)) +
    geom_point() +
    # ggtitle(paste0(d_group_in_title, "\n", gene_symbol, "_", ko1)) +
    ggtitle(paste0(d_group_in_title)) +
    geom_text_repel(point.padding      = 0.5,
                    min.segment.length = 0,
                    size               = 3,
                    box.padding        = 0.5,
                    max.overlaps       = 20,
                    show.legend        = FALSE) +
    scale_color_manual(values = col2use) +
    theme(
      panel.background = element_rect(fill = "transparent", color = NA),
      plot.background  = element_rect(fill = "transparent", color = NA),
      legend.background = element_rect(fill = "transparent", color = NA)
    )

  # Optionally save the plot
  if (save_plot && !is.null(volcano_figure_dir)) {
    # saved_figure_name <- paste0(d_group_in_title, "_", gene_name, "_", ko1, ".svg")
    #saved_figure_name <- paste0(d_group_in_title, "_", "volcano.png")
    ggsave(
      file   = file.path(volcano_figure_dir, "volcano_plot.png"),
      plot   = g,
      width  = 5,
      height = 3.2,
      bg     = "transparent",
      units  = "in"
    )
  }

  return(g)
}

g_volcano <- make_volcano_plot(
    res                = res_df,
    gene_symbol        = res_df$gene_symbol,
    ensembl_gene_id    = rownames(res_df),
    # gene_name          = gene_name,
    # d_group            = d_group,
    # ko1                = ko1,
    # fc0                = fc0,
    # p0                 = p0,
    clip_fc            = 3,
    volcano_figure_dir = counts_dir,
    save_plot          = TRUE
)

# Pre-filter genes with low counts (e.g. keep genes with at least 10 counts)
keep <- rowSums(counts(dds)) >= 10
dds_pca <- dds[keep, ]

# rlog or vst transformation for PCA plot, depending on number of samples
if (ncol(dds) <= 30) {
    standardized_counts <- rlog(dds_pca, blind = FALSE)
} else {
    standardized_counts <- vst(dds_pca, blind = FALSE)
}

# PCA plot of samples
pca_data <- plotPCA(standardized_counts, intgroup = "condition", ntop = nrow(standardized_counts), returnData = TRUE)
percent_var <- round(100 * attr(pca_data, "percentVar"))

# Give PCA plot labels
g <- ggplot(pca_data, aes(PC1, PC2, color = condition, label = name)) +
  ggtitle(paste0("PCA Plot of Samples Based on ", ifelse(ncol(dds) <= 30, "rlog-Transformed Counts", "Variance Stabilized Counts"))) +
  labs(subtitle = paste0("ntop = ", nrow(standardized_counts), " genes")) +
  geom_point(size = 3) +
  ggrepel::geom_text_repel() +
  xlab(paste0("PC1: ", percent_var[1], "% variance")) +
  ylab(paste0("PC2: ", percent_var[2], "% variance"))

ggsave(
  filename = file.path(counts_dir, "pca_plot.png"),
  plot = g,
  width = 8,
  height = 6,
  dpi = 300
)
