import io
import re

from django.core.files.base import ContentFile
from django.template import Context
from django.template.loader import get_template
from weasyprint import HTML
from weasyprint.fonts import FontConfiguration

# from xhtml2pdf import pisa


def preprocess_html_for_pdf(html):
    """
    Accommodates XHTML2PDF restrictions by replacing ``` with <pre> tags and <p></p> with <br />
    """
    closed_p_tags = html.count("</p>")
    # XHTML2PDF doesn't handle paragraphs too well as it inserts whitespace that cannot be styled,
    # so we're replacing those with line breaks to keep everything nice-looking

    ret = html.replace("</p>", "<br />", closed_p_tags - 1).replace("<p>", "")
    ret = re.sub(r"```([^`]*)```", r"<pre>\1</pre>", ret)
    ret = re.sub(r"`([^`]*)`", r"<pre style='display: inline-block;'>\1</pre>", ret)
    # the frontend editor adds `<p><br></p>` after lines, so after replacing the </p> there will be
    # duplicate <br />'s. coalesce the duplicate consecutive br tags into a single one to obtain
    # a single line break
    ret = re.sub(r"(<br\s*/?>)+", "<br />", ret)

    return ret


def render_to_pdf(template_src, context_dict):
    template = get_template(template_src)
    context = context_dict

    html = template.render(context)
    result = io.BytesIO()

    print(html)

    font_config = FontConfiguration()
    pdf_bin = HTML(string=html).write_pdf(font_config=font_config)
    pdf = ContentFile(pdf_bin)

    return pdf
