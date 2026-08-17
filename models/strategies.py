import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class Kind(Base):
    __tablename__ = 'kinds'
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(50), unique=True)
    strategies = relationship("Strategy", back_populates="kind")

# Определяем тестовую таблицу
class Strategy(Base):
    __tablename__ = 'strategies'
    id = sa.Column(sa.Integer, primary_key=True)
    number=sa.Column(sa.Integer, unique=True)
    name = sa.Column(sa.String(100))
    kind_id = sa.Column(sa.Integer, sa.ForeignKey('kinds.id'))  # Объявление форейндж кей
    kind = relationship("Kind", back_populates="strategies") #Связь для удобства
    subscribers=sa.Column(sa.Integer)
    annual_income=sa.Column(sa.Integer)
    min_summa=sa.Column(sa.Integer)
    link_text=sa.Column(sa.String(200))
    archived=sa.Column(sa.Boolean, nullable=False, server_default=sa.false(), default=False)
    history=relationship("History", back_populates="strategy") #Связь для удобства

class History(Base):
    __tablename__ = 'history'
    id = sa.Column(sa.Integer, primary_key=True)
    datetime=sa.Column(sa.Date())
    strategy_id=sa.Column(sa.Integer, sa.ForeignKey('strategies.id'))  # Объявление форейндж кей
    strategy=relationship("Strategy", back_populates="history") #Связь для удобства
    perc_income_day=sa.Column(sa.Numeric(precision=16, scale=6))
    perc_text=sa.Column(sa.String(40))
 