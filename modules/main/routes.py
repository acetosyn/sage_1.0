from flask import Blueprint, abort, redirect, render_template, url_for
from services.demo_data import NAV_ITEMS, PAGE_TITLES, RECENT_REQUESTS, ACTIVITIES, DEPARTMENTS

main_bp = Blueprint('main', __name__)

PAGES = set(PAGE_TITLES.keys())


def context(page):
    title, subtitle = PAGE_TITLES[page]
    return {
        'page': page,
        'page_title': title,
        'page_subtitle': subtitle,
        'nav_items': NAV_ITEMS,
        'requests': RECENT_REQUESTS,
        'activities': ACTIVITIES,
        'departments': DEPARTMENTS,
    }


@main_bp.route('/')
def index():
    return redirect(url_for('main.page', page='dashboard'))


@main_bp.route('/<page>')
def page(page):
    if page not in PAGES:
        abort(404)
    return render_template('app_shell.html', **context(page))


@main_bp.route('/partial/<page>')
def partial(page):
    if page not in PAGES:
        abort(404)
    return render_template(f'pages/{page}.html', **context(page))
