from contextlib import closing

from flask import Blueprint, current_app, jsonify, request

from . import catalog
from .risk import InputError, calculate_scenario


api = Blueprint('api', __name__)


@api.get('/healthz')
def health():
    with closing(catalog.connect(current_app.config['DATABASE'])) as db:
        db.execute('SELECT count(*) FROM instruments').fetchone()
    return {'status': 'ok'}


@api.get('/api/instruments')
def instruments():
    dataset = current_app.config['DATASET']
    with closing(catalog.connect(current_app.config['DATABASE'])) as db:
        db.execute('BEGIN')
        return {'dataset': dataset, 'snapshot': catalog.snapshot(db, dataset),
                'instruments': [catalog.encode_bond(bond) for bond in catalog.list_bonds(db, dataset)]}


@api.post('/api/calculate')
def calculate():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {'error': 'Передайте объект JSON со списком позиций.'}, 400
    dataset = current_app.config['DATASET']
    try:
        with closing(catalog.connect(current_app.config['DATABASE'])) as db:
            db.execute('BEGIN')
            if dataset == 'market':
                snapshot = catalog.snapshot(db, dataset)
                if snapshot is None or data.get('revision') != snapshot['revision']:
                    return {'error': 'Справочник обновился. Перезагрузите страницу.'}, 409
            result = calculate_scenario(data.get('positions'), lambda isin: catalog.find_bond(db, dataset, isin))
    except InputError as error:
        return {'error': str(error)}, 400
    return jsonify(result)


@api.app_errorhandler(413)
def too_large(_error):
    return {'error': 'Запрос слишком большой.'}, 413
