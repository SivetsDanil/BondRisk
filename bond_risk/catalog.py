import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from .risk import Bond


FIXTURES = Path(__file__).resolve().parents[1] / 'docs' / 'static' / 'js' / 'demo-data.js'
DECIMAL_FIELDS = ('face_value', 'quote_percent', 'fx_to_rub', 'modified_duration', 'convexity')


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db


def encode_bond(bond):
    data = asdict(bond)
    for key in DECIMAL_FIELDS:
        if data[key] is not None:
            data[key] = str(data[key])
    return data


def decode_bond(data):
    values = dict(data)
    for key in DECIMAL_FIELDS:
        if values.get(key) is not None:
            values[key] = Decimal(values[key])
    return Bond(**values)


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as db, db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS instruments (
                dataset TEXT NOT NULL CHECK (dataset IN ('demo', 'market')),
                isin TEXT NOT NULL,
                name TEXT NOT NULL,
                currency TEXT NOT NULL,
                face_value TEXT NOT NULL,
                quote_percent TEXT NOT NULL,
                fx_to_rub TEXT NOT NULL,
                coupon_type TEXT NOT NULL CHECK (coupon_type IN ('fixed', 'floating')),
                modified_duration TEXT,
                convexity TEXT,
                payments_per_year INTEGER,
                source TEXT NOT NULL,
                PRIMARY KEY (dataset, isin)
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                dataset TEXT PRIMARY KEY,
                market_date TEXT NOT NULL,
                fx_date TEXT NOT NULL,
                revision INTEGER NOT NULL
            );
        ''')
        fixture = FIXTURES.read_text(encoding='utf-8').strip()
        records = json.loads(fixture.removeprefix('window.bondRiskDemo = ').removesuffix(';'))
        for record in records:
            insert(db, 'demo', decode_bond(record), ignore_existing=True)


def insert(db, dataset, bond, ignore_existing=False):
    sql = '''
        INSERT INTO instruments (dataset, isin, name, currency, face_value, quote_percent,
            fx_to_rub, coupon_type, modified_duration, convexity, payments_per_year, source)
        VALUES (:dataset, :isin, :name, :currency, :face_value, :quote_percent,
            :fx_to_rub, :coupon_type, :modified_duration, :convexity, :payments_per_year, :source)
    '''
    if ignore_existing:
        sql += ' ON CONFLICT(dataset, isin) DO NOTHING'
    db.execute(sql, {'dataset': dataset, **encode_bond(bond)})


def find_bond(db, dataset, isin):
    row = db.execute('SELECT * FROM instruments WHERE dataset = ? AND isin = ?', (dataset, isin)).fetchone()
    return from_row(row) if row else None


def list_bonds(db, dataset):
    rows = db.execute('SELECT * FROM instruments WHERE dataset = ? ORDER BY rowid', (dataset,))
    return [from_row(row) for row in rows]


def from_row(row):
    data = dict(row)
    del data['dataset']
    return decode_bond(data)


def snapshot(db, dataset):
    row = db.execute('SELECT market_date, fx_date, revision FROM snapshots WHERE dataset = ?', (dataset,)).fetchone()
    return dict(row) if row else None


def replace_market(path, bonds, market_date, fx_date):
    with closing(connect(path)) as db, db:
        db.execute("DELETE FROM instruments WHERE dataset = 'market'")
        for bond in bonds:
            insert(db, 'market', bond)
        db.execute('''
            INSERT INTO snapshots (dataset, market_date, fx_date, revision) VALUES ('market', ?, ?, 1)
            ON CONFLICT(dataset) DO UPDATE SET market_date = excluded.market_date,
                fx_date = excluded.fx_date, revision = snapshots.revision + 1
        ''', (market_date.isoformat(), fx_date.isoformat()))
