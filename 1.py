import re

url = "https://www.comon.ru/strategies/1111116650/"
match = re.search(r'/(\d+)/?$', url)  # Ищем цифры в конце строки после слеша
if match:
    number = match.group(1)  # Извлекаем захваченную группу (цифры)
    print(number)  # Выводим извлеченные цифры
else:
    print("Номер не найден")
