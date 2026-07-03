from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, IntegerRangeField, BooleanField, IntegerField
from flask_wtf.file import FileField, FileAllowed
from wtforms.validators import DataRequired, Regexp, Optional, NumberRange

class SearchForm(FlaskForm):
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
        render_kw={"min": 10, "max": 50, "step": 1}
    )

    def validate(self, extra_validators=None):
        if super().validate(extra_validators):
            if not (self.query.data or self.genes.data):
                self.query.errors.append('A question or gene list is required')
                self.genes.errors.append('A gene list or a question is required')
                return False
            return True
        return True


class BwbForm(FlaskForm):
    file = FileField('fastq', validators=[Optional(), FileAllowed(['fastq'], 'Only .fastq allowed')])
    file_r2 = FileField('fastq', validators=[Optional(), FileAllowed(['fastq'], 'Only .fastq allowed')])
    sra_ids = TextAreaField('SRA IDs', validators=[Optional()])
    read_type = SelectField(
        'read_type',
        choices=[('single', 'Single-end'), ('paired', 'Paired-end')],
        default='single',
        validators=[Optional()]
    )
    workflow = SelectField(
        'alignment_name',
        choices=[
            ('star_salmon_short_yin', 'star_salmon_short_yin'),
            ('star_salmon_short_ryan', 'star_salmon_short_ryan'),
            ('morphic_bulk_rna_seq', 'MorPhiC Bulk RNA-seq'),
        ],
        default='star_salmon_short_yin',
        validators=[DataRequired()]
    )

    def validate(self, extra_validators=None):
        if super().validate(extra_validators):
            if self.read_type.data == 'paired' and (not self.file_r2.data or not self.file.data):
                self.file_r2.errors.append('Must upload both files for paired end')
                return False
            return True
        return True


def create_results_table_form(studies_data):
    """Generate a WTForms form with one BooleanField per study ID (used by search results)."""
    class ResultsTableForm(FlaskForm):
        pass

    for gse_id in studies_data:
        setattr(ResultsTableForm, gse_id, BooleanField(gse_id, default=False))

    return ResultsTableForm
