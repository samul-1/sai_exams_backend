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


def escape_unsafe_text(text):
    """
    Escapes unsafe characters in user-submitted text in order to safely use
    them in html templates
    """
    return text.replace("<", "&lt;").replace(">", "&gt;")


def render_to_pdf(template_src, context_dict, render_tex=False):
    template = get_template(template_src)
    context = context_dict

    print(context)

    html = template.render(context)

    if render_tex:
        html = tex_to_svg(html)

    font_config = FontConfiguration()
    pdf_bin = HTML(string=html).write_pdf(font_config=font_config)
    pdf = ContentFile(pdf_bin)

    return pdf
