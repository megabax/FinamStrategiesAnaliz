import re

BADGES = frozenset({'ИИС', 'NEW', 'Копилка', 'Бонус'})


class StrategyInfo:
    # ['Консервативный', '128', 'ИИС', 'Синергия New', 'Среднегодовая доходность', '110 %', 'Минимальная сумма',
    #  'от 370 000 ₽']
    # кривой, значение
    # с
    # индексом
    # 3
    # должно
    # быть
    # 'среднегодовая доходность'
    # https: // www.comon.ru / strategies / 115412 / кривая[
    #     'Консервативный', '128', 'ИИС', 'Синергия New', 'Среднегодовая доходность', '110 %', 'Минимальная сумма', 'от 370 000 ₽']

    def __init__(self,ls, link):
        self.is_succes=False
        self.link = link
        self.fill_from(ls)
        #link, kind, subscribers, name, annual_income, min_summa
        #['Агрессивный', '180', 'Росточек', 'Среднегодовая доходность', '332 %', 'Минимальная сумма', 'от 50 000 ₽'], '116650')

    def string_percentage_to_float(self,s):
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
                percentage = number
                return percentage
            except ValueError:
                return None  # Если что-то пошло не так с преобразованием в float
        else:
            return None

    def get_min_summa(self,s):
        """
        Извлекает числовую сумму из строки вида 'от 50 000 ₽'.

        Args:
          текст: Строка, которую нужно проанализировать.

        Returns:
          Целое число, представляющее сумму, или None, если строка не соответствует формату.
        """
        template = r"от\s*([\d\s]+)\s*₽"  # Регулярное выражение
        res = re.match(template, s)

        if res:
            summa_str = res.group(1).replace(" ", "")  # Удаляем пробелы
            try:
                summ = int(summa_str)
                return summ
            except ValueError:
                return None  # Если не удалось преобразовать в целое число
        else:
            return None  # Если строка не соответствует шаблону

    def fill_annual_income(self,ls):
        an = self.string_percentage_to_float(ls[4 + self.shifh])
        if an is None:
            print(ls[4 + self.shifh], 'не число с процентами')
            return False
        self.annual_income = an
        return True

    def fill_from(self,ls):
        self.shifh = 0
        if type(ls[0 + self.shifh]) == str:
            self.kind = ls[0 + self.shifh]
        else:
            print(ls, "не строка")
            return
        if ls[1].isdigit():
            self.subscribers = int(ls[1])
        else:
            print(ls[1 + self.shifh], "не число")
            return

        while 2 + self.shifh < len(ls) and ls[2 + self.shifh] in BADGES:
            self.shifh += 1

        self.name = ls[2 + self.shifh]
        income_label_idx = 3 + self.shifh
        if ls[income_label_idx].lower() == 'среднегодовая доходность':
            if not self.fill_annual_income(ls):
                return
        else:
            print(
                ls,
                f"кривой, значение с индексом {income_label_idx} "
                f"должно быть 'среднегодовая доходность'",
            )
            return
        if ls[5 + self.shifh].lower() == 'минимальная сумма':
            ms = self.get_min_summa(ls[6 + self.shifh])
            if ms is None:
                print(ls[6 + self.shifh], 'не содержит минимальную сумму')
                return
            self.min_summa = ms
        self.is_succes = True
