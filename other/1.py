def extract_percentage(data_string: str) -> float:
    """
    Извлекает значение процента из строки формата "Сумма / Процент %"
    и преобразует его в тип float.

    Обрабатывает пробелы как группировочные разделители.

    :param data_string: Входная строка (например, "30 668 ₽ / 6.13 %")
    :return: Значение процента в виде float (например, 6.13)
    :raises ValueError: Если строка имеет неверный формат или процент не может быть преобразован.
    """
    # 1. Разделяем строку по разделителю "/"
    parts = data_string.split('/')

    if len(parts) < 2:
        raise ValueError("Строка имеет неверный формат: отсутствует разделитель '/'")

    # Вторая часть (индекс 1) содержит процент. Удаляем пробелы по краям.
    percentage_str_raw = parts[1].strip()

    # 2. Очищаем строку от лишних символов

    # Удаляем знак процента (%)
    cleaned_str = percentage_str_raw.replace('%', '')

    # Удаляем все пробелы (группировочные разделители)
    cleaned_str = cleaned_str.replace(' ', '')

    # Удаляем оставшиеся пробелы по краям (если они появились)
    cleaned_str = cleaned_str.strip()

    # 3. Преобразуем очищенную строку в float
    try:
        result_float = float(cleaned_str)
        return result_float
    except ValueError:
        raise ValueError(f"Не удалось преобразовать значение '{cleaned_str}' в число.")


# --- Примеры использования ---

test_strings = [
    "30 668 ₽ / 6.13 %",
    "10000 / 12.5 %",
    "500 000 ₽ / 0.75%",  # Без пробела перед %
    "1 000 000 / 1 000.5 %"  # Процент с группировочным разделителем (пробелом)
]

for s in test_strings:
    try:
        percentage = extract_percentage(s)
        print(f"Строка: '{s}' -> Процент (float): {percentage} (Тип: {type(percentage)})")
    except ValueError as e:
        print(f"Ошибка обработки '{s}': {e}")

