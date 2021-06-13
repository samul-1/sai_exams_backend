import io
import re

from django.core.files.base import ContentFile
from django.template import Context
from django.template.loader import get_template
from xhtml2pdf import pisa


def preprocess_html_for_pdf(html):
    """
    Accommodates XHTML2PDF restrictions by replacing ``` with <pre> tags and <p></p> with <br />
    """
    closed_p_tags = html.count("</p>")
    ret = html.replace("</p>", "", closed_p_tags - 1).replace("<p>", "")

    ret = re.sub(r"```([^`]*)```", r"<pre>\1</pre>", ret)

    return ret


def render_to_pdf(template_src, context_dict):
    template = get_template(template_src)
    context = context_dict

    html = template.render(context)
    result = io.BytesIO()

    # print(html)
    # pdf = pisa.pisaDocument(io.BytesIO(html.encode("ISO-8859-1")), result)
    print(html)
    # if not pdf.err:
    #     return result.getvalue()
    pdf = ContentFile(b"")
    pisa_status = pisa.CreatePDF(html, dest=pdf)
    return pdf

    return "error"
