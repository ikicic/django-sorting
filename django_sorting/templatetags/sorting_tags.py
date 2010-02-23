from urlparse import urlunparse

from django import template
from django.conf import settings
from django.http import Http404
from django.utils.http import urlquote, urlencode

register = template.Library()

DEFAULT_SORT_UP = getattr(settings, 'DEFAULT_SORT_UP' , '&uarr;')
DEFAULT_SORT_DOWN = getattr(settings, 'DEFAULT_SORT_DOWN' , '&darr;')
INVALID_FIELD_RAISES_404 = getattr(settings,
        'SORTING_INVALID_FIELD_RAISES_404' , False)

sort_directions = {
    'asc': {'icon':DEFAULT_SORT_UP, 'inverse': 'desc'},
    'desc': {'icon':DEFAULT_SORT_DOWN, 'inverse': 'asc'},
    '': {'icon':DEFAULT_SORT_DOWN, 'inverse': 'asc'},
}

def anchor(parser, token):
    """
    Parses a tag that's supposed to be in this format: {% anchor field title fragment %}
    """
    bits = token.contents.split()
    if not (2 < len(bits) < 5):
        raise TemplateSyntaxError, "anchor tag takes at least 2 arguments"
    title = bits[2]
    try:
        fragment = bits[3]
    except IndexError:
        fragment = ''
    return SortAnchorNode(bits[1].strip(), title.strip(), fragment.strip())

class SortAnchorNode(template.Node):
    """
    Renders an <a> HTML tag with a link which href attribute 
    includes the field on which we sort and the direction.
    and adds an up or down arrow if the field is the one 
    currently being sorted on.

    Eg.
        {% anchor name1,name2 Name fragment %} generates
        <a href="?sort=name1,name2#fragment" title="Name">Name</a>

    """
    def __init__(self, field, title, fragment):
        self.field = template.Variable(field)
        self.title = title and template.Variable(title)
        self.fragment = fragment and template.Variable(fragment)

    def render(self, context):
        request = context['request']
        getvars = request.GET.copy()
        field = self.field.resolve(context)
        title = self.title and self.title.resolve(context)
        fragment = self.fragment and self.fragment.resolve(context)

        if getattr(request, 'sort', getvars.get('sort', '')) == field:
            sortdir = getattr(request, 'direction', getvars.get('direction', ''))
            getvars['direction'] = sort_directions[sortdir]['inverse']
            icon = sort_directions[sortdir]['icon']
            css_class = "active " + getvars['direction']
        else:
            getvars['direction'] = 'desc'
            css_class = icon = ''
        getvars['sort'] = field
        if icon:
            title = "%s %s" % (title, icon)
        else:
            title = title

        url = urlunparse(('', '', '', None, getvars.urlencode(), fragment))
        return '<a href="%s" class="%s" title="%s">%s</a>' % (url, css_class, title, title)

def autosort(parser, token):
    bits = token.contents.split()
    if not (1 < len(bits) < 5):
        raise template.TemplateSyntaxError, "autosort tag takes exactly one argument"
    try:
        accepted_fields = bits[2]
    except IndexError:
        accepted_fields = None

    try:
        default_ordering = bits[3]
    except IndexError:
        default_ordering = None

    return SortedDataNode(bits[1], accepted_fields, default_ordering)

class SortedDataNode(template.Node):
    """
    Automatically sort a queryset with {% autosort queryset [accepted_fields [default_ordering]] %}
    """
    def __init__(self, queryset_var, accepted_fields=None, default_ordering=None):
        self.queryset_var = template.Variable(queryset_var)
        self.accepted_fields = accepted_fields and template.Variable(accepted_fields)
        self.default_ordering = default_ordering and template.Variable(default_ordering)

    def get_fields(self, request, accepted_fields=None, default_ordering=None):
        fields = getattr(request, 'sort', request.REQUEST.get('sort', ''))
        if not fields and default_ordering:
            fields = request.sort = default_ordering
        direction = getattr(request, 'direction', request.REQUEST.get('direction', 'desc')) =='desc' and '-' or ''

        fields = [
            (direction == '-' and field.startswith('-') and field[1:]) or direction + field
            for field in fields.split(',') if field and (
                not accepted_fields
                or field in accepted_fields
                or (field.startswith('-') and field[1:] in accepted_fields)
            )
        ]
        return fields

    def render(self, context):
        key = self.queryset_var.var
        value = self.queryset_var.resolve(context)
        request = context['request']
        accepted_fields = \
            self.accepted_fields and [field.strip() for field in self.accepted_fields.resolve(context).split(',')]
        default_ordering = self.default_ordering and self.default_ordering.resolve(context)

        order_by = value.query.order_by + self.get_fields(
            request,
            accepted_fields,
            default_ordering
        )

        try:
            context[key] = value.order_by(*order_by)
        except template.TemplateSyntaxError:
            if INVALID_FIELD_RAISES_404:
                raise Http404('Invalid field sorting. If DEBUG were set to ' +
                'False, an HTTP 404 page would have been shown instead.')
            context[key] = value
        return ''

anchor = register.tag(anchor)
autosort = register.tag(autosort)

