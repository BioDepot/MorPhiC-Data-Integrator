from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, IntegerRangeField, BooleanField
from flask_wtf.file import FileField, FileAllowed
from wtforms.validators import DataRequired, Regexp, Optional

class SearchForm(FlaskForm):
    """
    Form for performing a search to Sample Explorer
    
    Attributes:
        query (StringField): A text field where the user enters a question or search query.
        genes (TextAreaField): A text area field for set of genes.
        expansion_stratergy (SelectField): A select field for a choice of different expanstion strategies.
        size (IntegerRangeField): A integer range field for selecting the amount of lines returned from the search result
    """
    query = StringField(
        'query',
        render_kw={"placeholder": "This text query usually describes the experiment"},
        validators=[Regexp(r'^[a-zA-Z0-9\s!.,:;?()"&-/\'`]*$', message='Only alphanumeric characters, common punctuation and spaces are allowed')]
    )
    genes = TextAreaField(
        'genes',
        render_kw={"rows": 5},
        validators=[Regexp(r'^[a-zA-Z0-9\s\n!.,:;?()"&-/\'`]*$', message='Only alphanumeric characters, common punctuation, new lines and spaces are allowed')]
    )
    expansion_strategy = SelectField(
        'expansion-strategy',
        choices=[('semantic_semantic', 'Semantic/Semantic'), ('semantic_transcriptome', 'Semantic/Transcriptome')], 
        default='semantic_semantic',
        validators=[DataRequired()]
    )
    size = IntegerRangeField(
        'View top 20 results',
        default=20,
        validators=[DataRequired()],
        render_kw={
            "min": 10, 
            "max": 50, 
            "step": 1
        }
    )

    def validate(self, extra_validators = None):
        """
        Custom validation to check that a least a search or a list of genes were provided
        
        Returns:
            bool: True if validation passes, False otherwise
        """
        if super().validate(extra_validators):
            if not (self.query.data or self.genes.data):
                self.query.errors.append('A question or gene list is required')
                self.genes.errors.append('A gene list or a question is required')
                return False
            else:
                return True
        else:
            return True


class BwbForm(FlaskForm):
    """
    Form for choosing the parameters for Bwb
    
    Attributes:
        file (FileField): A file input field for uploading a file
        file_r2 (FileField): A file input field for uploading a file
        workflow (SelectField): A select field for a choice of different workflows available
    """
    file = FileField('fastq', validators=[Optional(), FileAllowed(['fastq'], 'Only .fastq allowed')])
    file_r2 = FileField('fastq', validators=[Optional(), FileAllowed(['fastq'], 'Only .fastq allowed')])
    read_type = SelectField(
        'read_type',
        choices=[('single', 'Single-end'), ('paired', 'Paired-end')],
        default='single',
        validators=[Optional()]
    )
    workflow = SelectField(
        'alignment_name',
        choices=[('star_salmon_short_yin', 'star_salmon_short_yin'), ('star_salmon_short_ryan', 'star_salmon_short_ryan'), ('morphic_bulk_rna_seq', 'MorPhiC Bulk RNA-seq')], 
        default='star_salmon_short_yin',
        validators=[DataRequired()]
    )

    def validate(self, extra_validators = None):
        """
        Custom validation to check that when read type is 'paired' there are two files uploaded
        
        Returns:
            bool: True if validation passes, False otherwise
        """
        if super().validate(extra_validators):
            if self.read_type.data == 'paired' and (not self.file_r2.data or not self.file.data):
                self.file_r2.errors.append('Must upload both files for paired end')
                return False
            else:
                return True
        else:
            return True

class GroupForm(FlaskForm):
    """
    Form for creating a new SRR ID group.
    
    Attributes:
        group_a (StringField): A text field where the user enters a group name.
        group_b (StringField): A text field where the user enters a group name.
    """
    group_a = StringField(
        'new_group',
        render_kw={"placeholder": "Group name."},
        validators=[
            DataRequired(),
            Regexp(r'^[a-zA-Z0-9\s!.,:;?()"&-/\'`]*$', message='Only alphanumeric characters, common punctuation and spaces are allowed')
        ]
    )
    group_b = StringField(
        'new_group',
        render_kw={"placeholder": "Group name"},
        validators=[
            DataRequired(),
            Regexp(r'^[a-zA-Z0-9\s!.,:;?()"&-/\'`]*$', message='Only alphanumeric characters, common punctuation and spaces are allowed')
        ]
    )

def create_results_table_form(studies_data):
    """
    Generate Form for selecting gse id's.
    
    This function will take studies data and create a Flask-WTF form with a checkbox input for each gse id.
    
    Args:
        studies_data (list of string): A list of gse id's.
        
    Returns:
        FlaskForm: A dynamically generated Flask-WTF form with BooleanField(s) for each dictionary attribute of the studies_data list.

    Example:
        studies_data = ["GSEID", "GSEID2"]
        form = create_results_table_form(studies_data)
    """
    class ResultsTableForm(FlaskForm):
        # Dynamically create checkboxes for each study
        pass

    for gse_id in studies_data:
        checkbox = BooleanField(gse_id, default=False)
        setattr(ResultsTableForm, gse_id, checkbox)

    return ResultsTableForm

def create_srr_form(srr_list, groups=None):
    """
    Generate Form for selecting SRR ID's.
    
    This function will take SRR ID's and create a Flask-WTF form with a select dropdown containing group options for each SRR ID
    
    Args:
        srr_list (set of string): A set of SRR ID's.
        groups (set of string): A set of group names.
        
    Returns:
        FlaskForm: A dynamically generated Flask-WTF form with SelectField(s) with groups as choices for each SRR ID.

    Example:
        studies_data= {"SRRID", "SRRID2"}
        group_names = {"Group1", "Group2"} 
        form = create_srr_form(srr_list, group_names)
    """
    class SRRForm(FlaskForm):
        # Dynamically create checkboxes for each study
        pass

    if groups:
        for srr_id in srr_list:
            select_group = SelectField(
                srr_id,
                choices=[('', 'Add to group')] + [(group_name, group_name) for group_name in set(groups)],
                default='',
                validators=[Optional()]
            )
            setattr(SRRForm, srr_id, select_group)
    else:
        for srr_id in srr_list:
            select_group = SelectField(
                srr_id,
                choices=[('', 'Add to group')],
                default='',
                validators=[Optional()]
            )
            setattr(SRRForm, srr_id, select_group)

    return SRRForm

def create_morphic_form(studies_data):
    """
    Generate Form for selecting gse id's.
    
    This function will take studies data and create a Flask-WTF form with a checkbox input for each gse id.
    
    Args:
        studies_data (list of string): A list of gse id's.
        
    Returns:
        FlaskForm: A dynamically generated Flask-WTF form with BooleanField(s) for each dictionary attribute of the studies_data list.

    Example:
        studies_data = ["GSEID", "GSEID2"]
        form = create_create_morphic_form(studies_data)
    """
    class MorphicForm(FlaskForm):
        # Dynamically create checkboxes for each study
        pass

    for gse_id in studies_data:
        checkbox = BooleanField(gse_id, default=False)
        setattr(MorphicForm, gse_id, checkbox)

    return MorphicForm