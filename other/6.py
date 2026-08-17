"""Печать SQLAlchemy URL из .env (без хардкода hostname)."""

from lib.env import get_database_url

print(get_database_url())
