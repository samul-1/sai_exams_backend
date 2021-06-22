import io
import re
import subprocess

from django.core.files.base import ContentFile
from django.template import Context
from django.template.loader import get_template
from weasyprint import HTML
from weasyprint.fonts import FontConfiguration

from .tex import tex_to_svg


def preprocess_html_for_pdf(html):
    """
    Replaces ``` with <pre> tags and <p></p> with <br />
    """
    closed_p_tags = html.count("</p>")

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

    html = tex_to_svg(template.render(context))

    print(html)

    font_config = FontConfiguration()
    pdf_bin = HTML(string=html).write_pdf(font_config=font_config)
    pdf = ContentFile(pdf_bin)

    return pdf
