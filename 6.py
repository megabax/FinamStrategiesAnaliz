SERVER = 'MEGABAX\SQLEXPRESS' #  'localhost' or 'your_server_name' or 'your_server_address'
DATABASE_NAME = 'FinamStrategies'
USERNAME = 'your_username'
PASSWORD = 'your_password'
DRIVER = 'ODBC Driver 17 for SQL Server' # Or appropriate driver installed

# Строка подключения
#CONNECTION_STRING = f"mssql+pyodbc://{USERNAME}:{PASSWORD}@{SERVER}/{DATABASE_NAME}?driver={DRIVER}"
# Alternative connection string for Windows Authentication (remove USERNAME and PASSWORD)
CONNECTION_STRING = f"mssql+pyodbc://{SERVER}/{DATABASE_NAME}?driver={DRIVER}&Trusted_Connection=yes"
print(CONNECTION_STRING)