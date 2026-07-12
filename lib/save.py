import sqlalchemy as sa
from datetime import datetime
from sqlalchemy.orm import sessionmaker

from models.strategies import Base, Strategy, Kind, History

# Параметры подключения к MSSQL
SERVER = 'MEGABAX\SQLEXPRESS' #  'localhost' or 'your_server_name' or 'your_server_address'
DATABASE_NAME = 'FinamStrategies'
USERNAME = 'your_username'
PASSWORD = 'your_password'
DRIVER = 'ODBC Driver 17 for SQL Server' # Or appropriate driver installed

# Строка подключения
#CONNECTION_STRING = f"mssql+pyodbc://{USERNAME}:{PASSWORD}@{SERVER}/{DATABASE_NAME}?driver={DRIVER}"
# Alternative connection string for Windows Authentication (remove USERNAME and PASSWORD)
CONNECTION_STRING = f"mssql+pyodbc://{SERVER}/{DATABASE_NAME}?driver={DRIVER}&Trusted_Connection=yes"  # If using Windows Authentication

def check_and_create_database(engine, database_name):
    """Проверяет наличие базы данных и создает её, если она не существует."""
    conn = None  # Initialize conn to None
    try:
        conn = engine.connect()
        result = conn.execute(sa.text(f"SELECT 1 FROM sys.databases WHERE name = '{database_name}'"))
        if result.scalar() is None: # <--- Исправлено здесь
            conn.execute(sa.text(f"CREATE DATABASE {database_name}"))
            print(f"База данных '{database_name}' успешно создана.")
        else:
            print(f"База данных '{database_name}' уже существует.")

    except sa.exc.ProgrammingError as e:
        # This usually means the database does not exist *and* you don't have
        # permission to enumerate databases.  Good luck!
        if 'Cannot open database "master"' in str(e):
            print(f"Ошибка: не удалось подключиться к базе данных 'master'. Проверьте настройки подключения или разрешения.")
            exit(1)  # Exit the program as we can't proceed

        print(f"Ошибка при проверке/создании базы данных: {e}")
        exit(1)
    except Exception as e:
        print(f"Неожиданная ошибка: {e}")
        exit(1)
    finally:
        if conn:
            conn.close() # Close connection if it exists


def find_or_create_kind(session, kind):
    existing_kind = session.query(Kind).filter_by(name=kind).first()
    if existing_kind:
        return existing_kind
    else:
        new_kind = Kind(name=kind)
        session.add(new_kind)
        session.commit()
        return new_kind

def history_record_existis(session,strategy_id,datetime):
    existing_record = session.query(History).filter(
        History.strategy_id == strategy_id,
        History.datetime == datetime
    ).first()
    if existing_record:
        return True
    else:
        return False

def delete_strategy_history_period(session, strategy_id, from_date, to_date):
    if isinstance(from_date, datetime):
        from_date = from_date.date()
    if isinstance(to_date, datetime):
        to_date = to_date.date()

    deleted = session.query(History).filter(
        History.strategy_id == strategy_id,
        History.datetime >= from_date,
        History.datetime <= to_date,
    ).delete(synchronize_session=False)
    session.commit()
    return deleted


def save_history_record_to_db(strategy_id, record_datetime, perc, perc_text, replace=False):
    session = create_session()
    if isinstance(record_datetime, datetime):
        record_date = record_datetime.date()
    else:
        record_date = record_datetime

    existing_record = session.query(History).filter(
        History.strategy_id == strategy_id,
        History.datetime == record_date,
    ).first()
    if existing_record:
        if replace:
            existing_record.perc_income_day = perc
            existing_record.perc_text = perc_text
            session.commit()
        return

    new_record = History(
        strategy_id=strategy_id,
        datetime=record_date,
        perc_income_day=perc,
        perc_text=perc_text,
    )
    session.add(new_record)
    session.commit()

def get_active_strategies(session):
    return session.query(Strategy).filter(Strategy.archived == False).order_by(Strategy.id).all()


def create_session():
    engine = sa.create_engine(CONNECTION_STRING)
    engine.connect()
    check_and_create_database(engine, DATABASE_NAME)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    return session

def save_strategies_to_db(links, skip_existing=False):
    session = create_session()
    added = 0
    skipped = 0
    for link in links:
        link_text, info, number = link
        kind = find_or_create_kind(session, info.kind)

        existing_record = session.query(Strategy).filter_by(number=number).first()
        if existing_record:
            if skip_existing:
                skipped += 1
                continue
            existing_record.name = info.name
            existing_record.kind = kind
            existing_record.subscribers = info.subscribers
            existing_record.annual_income = info.annual_income
            existing_record.min_summa = info.min_summa
            existing_record.link_text = link_text
        else:
            new_record = Strategy(
                number=number, name=info.name, kind=kind,
                subscribers=info.subscribers, annual_income=info.annual_income,
                min_summa=info.min_summa, link_text=link_text,
            )
            session.add(new_record)
            added += 1
        session.commit()
    return added, skipped