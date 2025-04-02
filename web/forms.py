from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, IntegerRangeField
from wtforms.validators import DataRequired, Regexp

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
    Form for choosing the ;arameters for Bwb
    
    Attributes:
        workflow (SelectField): A select field for a choice of different workflows available
    """
    workflow = SelectField(
        'alignment_name',
        choices=[('GSE169687', 'star_salmon_short_yin'), ('GSE224615', 'star_salmon_short_ryan'), ('TEST', 'test')], 
        default='GSE169687',
        validators=[DataRequired()]
    )
