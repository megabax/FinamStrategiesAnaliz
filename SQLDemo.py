import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from lib.env import get_database_name, get_database_url

Base = declarative_base()


class TestTable(Base):
    __tablename__ = 'test_table'

    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(255))


def check_and_create_database(engine, database_name):
    """Проверяет наличие базы данных и создает её, если она не существует."""
    conn = None
    try:
        conn = engine.connect()
        result = conn.execute(sa.text(f"SELECT 1 FROM sys.databases WHERE name = '{database_name}'"))
        if result.scalar() is None:
            conn.execute(sa.text(f"CREATE DATABASE {database_name}"))
            print(f"База данных '{database_name}' успешно создана.")
        else:
            print(f"База данных '{database_name}' уже существует.")

    except sa.exc.ProgrammingError as e:
        if 'Cannot open database "master"' in str(e):
            print("Ошибка: не удалось подключиться к базе данных 'master'. Проверьте настройки подключения или разрешения.")
            exit(1)

        print(f"Ошибка при проверке/создании базы данных: {e}")
        exit(1)
    except Exception as e:
        print(f"Неожиданная ошибка: {e}")
        exit(1)
    finally:
        if conn:
            conn.close()


def main():
    try:
        connection_string = get_database_url()
        database_name = get_database_name(connection_string)
        engine = sa.create_engine(connection_string)
        engine.connect()

        check_and_create_database(engine, database_name)
        engine.dispose()

        engine = sa.create_engine(connection_string)

        Base.metadata.create_all(engine)
        print("Таблица 'test_table' успешно создана (если она еще не существовала).")

        Session = sessionmaker(bind=engine)
        session = Session()

        if session.query(TestTable).count() == 0:
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
