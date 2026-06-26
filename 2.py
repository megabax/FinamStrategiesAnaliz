import re

def string_percentage_to_float(s):
    """
    Проверяет, является ли строка 's' числом с процентами (например, '332 %'),
    и преобразует ее в число с плавающей точкой (float), представляющее процент
    (например, 3.32). В противном случае возвращает None.
    """
    match = re.match(r'^\s*([+-]?\d+(\.\d*)?|\.\d+)\s*%\s*$', s)
    if match:
        try:
            number_str = match.group(1)
            number = float(number_str)
            percentage = number / 100.0
            return percentage
        except ValueError:
            return None  # Если что-то пошло не так с преобразованием в float
    else:
        return None

# Примеры использования:
string_percentage = "332 %"
result = string_percentage_to_float(string_percentage)
if result is not None:
    print(f"Строка '{string_percentage}' успешно преобразована в число: {result}")
    print(f"Тип результата: {type(result)}")
else:
    print(f"Строка '{string_percentage}' не является числом с процентами.")

string_percentage = "  -12.5% "
result = string_percentage_to_float(string_percentage)
if result is not None:
    print(f"Строка '{string_percentage}' успешно преобразована в число: {result}")
    print(f"Тип результата: {type(result)}")
else:
    print(f"Строка '{string_percentage}' не является числом с процентами.")

string_percentage = "abc%"
result = string_percentage_to_float(string_percentage)
if result is not None:
    print(f"Строка '{string_percentage}' успешно преобразована в число: {result}")
    print(f"Тип результата: {type(result)}")
else:
    print(f"Строка '{string_percentage}' не является числом с процентами.")

string_percentage = "12"
result = string_percentage_to_float(string_percentage)
if result is not None:
    print(f"Строка '{string_percentage}' успешно преобразована в число: {result}")
    print(f"Тип результата: {type(result)}")
else:
    print(f"Строка '{string_percentage}' не является числом с процентами.")

string_percentage = "12 % bla"
result = string_percentage_to_float(string_percentage)
if result is not None:
    print(f"Строка '{string_percentage}' успешно преобразована в число: {result}")
    print(f"Тип результата: {type(result)}")
else:
    print(f"Строка '{string_percentage}' не является числом с процентами.")
