import os
from datetime import date
from pathlib import Path

import click
from flask import Flask, Response, redirect, send_from_directory, url_for
from waitress import serve

from bond_risk import catalog
from bond_risk.api import api
from bond_risk.market import cbr_rates, load_market_csv
from bond_risk.risk import InputError


ROOT = Path(__file__).resolve().parent
DOCS = ROOT / 'docs'


def create_app(test_config=None):
    app = Flask(__name__, instance_path=str(ROOT / 'instance'), static_folder=DOCS / 'static')
    app.config.update(
        DATABASE=os.environ.get('DV01_DATABASE', str(Path(app.instance_path) / 'catalog.sqlite3')),
        DATASET=os.environ.get('DV01_DATASET', 'demo'),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config is not None:
        app.config.update(test_config)

    database = app.config['DATABASE']
    dataset = app.config['DATASET']
    if dataset not in ('demo', 'market'):
        raise ValueError('DV01_DATASET должен быть demo или market.')
    catalog.initialize(database)
    app.register_blueprint(api)

    @app.get('/')
    @app.get('/index.html')
    def index():
        return send_from_directory(DOCS, 'index.html')

    @app.get('/instruments.html')
    def instruments():
        return send_from_directory(DOCS, 'instruments.html')

    @app.get('/method.html')
    def method():
        return send_from_directory(DOCS, 'method.html')

    @app.get('/instruments/')
    def previous_instruments_url():
        return redirect(url_for('instruments'))

    @app.get('/method/')
    def previous_method_url():
        return redirect(url_for('method'))

    @app.get('/mode.js')
    def mode():
        return Response('window.bondRiskServer = true;', mimetype='application/javascript')

    @app.cli.command('import-market')
    @click.argument('csv_path', type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.option('--date', 'market_date', required=True, type=click.DateTime(formats=['%Y-%m-%d']))
    def import_market(csv_path, market_date):
        date_requested = market_date.date()
        if date_requested > date.today():
            raise click.ClickException('Дата рыночного снимка находится в будущем.')
        try:
            fx_date, rates = cbr_rates(date_requested)
            bonds = load_market_csv(csv_path, rates)
            catalog.replace_market(database, bonds, date_requested, fx_date)
        except (InputError, OSError, UnicodeError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(f'Загружено бумаг: {len(bonds)}. Курсы Банка России от {fx_date:%d.%m.%Y}.')

    return app


def main():
    app = create_app()
    host = os.environ.get('DV01_HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8080'))
    print(f'Экран расчёта DV01: http://{host}:{port}', flush=True)
    serve(app, host=host, port=port, max_request_body_size=app.config['MAX_CONTENT_LENGTH'])


if __name__ == '__main__':
    main()
