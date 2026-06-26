import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# Параметры подключения к MSSQL
SERVER = 'MEGABAX\SQLEXPRESS' #  'localhost' or 'your_server_name' or 'your_server_address'
DATABASE_NAME = 'TestDatabase'
USERNAME = 'your_username'
PASSWORD = 'your_password'
DRIVER = 'ODBC Driver 17 for SQL Server' # Or appropriate driver installed

# Строка подключения
#CONNECTION_STRING = f"mssql+pyodbc://{USERNAME}:{PASSWORD}@{SERVER}/{DATABASE_NAME}?driver={DRIVER}"
# Alternative connection string for Windows Authentication (remove USERNAME and PASSWORD)
CONNECTION_STRING = f"mssql+pyodbc://{SERVER}/{DATABASE_NAME}?driver={DRIVER}&Trusted_Connection=yes"  # If using Windows Authentication


Base = declarative_base()

# Определяем тестовую таблицу
class TestTable(Base):
    __tablename__ = 'test_table'

    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(255))


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




def main():
    """Основная функция для подключения к базе данных, её создания (если необходимо) и создания таблицы."""

    try:
        engine = sa.create_engine(CONNECTION_STRING)
        engine.connect() # Test the connection immediately

        # Check/Create the database.  Critically, do this *before* trying
        # to reflect the engine's structure or proceed with ORM setup
        check_and_create_database(engine, DATABASE_NAME)
        engine.dispose() # Required to close any lingering connections from check_and_create_database

        # Recreate engine *after* database existence is confirmed
        engine = sa.create_engine(CONNECTION_STRING)


        # Создаем таблицы (если они еще не созданы)
        Base.metadata.create_all(engine)
        print("Таблица 'test_table' успешно создана (если она еще не существовала).")

        # Пример использования сессии для добавления данных
        Session = sessionmaker(bind=engine)
        session = Session()

        # Проверяем, есть ли уже записи в таблице
        if session.query(TestTable).count() == 0:  # Correct way to get row count
            # Создаем тестовую запись
            new_record = TestTable(name='Test Record')
            session.add(new_record)
            session.commit()
            print("Добавлена тестовая запись.")
        else:
            print("В таблице уже есть записи.  Пропускаем добавление тестовой записи.")

        session.close()


    except sa.exc.SQLAlchemyError as e:
        print(f"Ошибка SQLAlchemy: {e}")
    except Exception as e:
        print(f"Общая ошибка: {e}")


if __name__ == "__main__":
    main()
