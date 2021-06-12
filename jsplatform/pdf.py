import io

from django.core.files.base import ContentFile
from django.template import Context
from django.template.loader import get_template
from xhtml2pdf import pisa


def render_to_pdf(template_src, context_dict):
    template = get_template(template_src)
    context = context_dict

    html = template.render(context)
    result = io.BytesIO()

    # print(html)
    pdf = pisa.pisaDocument(io.BytesIO(html.encode("ISO-8859-1")), result)
    if not pdf.err:
        return result.getvalue()

    return "error"
