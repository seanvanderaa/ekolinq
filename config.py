# config.py
import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'my_dev_secret_key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URI', 'sqlite:///ekolinq.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False