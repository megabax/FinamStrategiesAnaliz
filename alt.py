# Переход по указанному URL
driver.get(url)
divs=driver.find_elements(By.CLASS_NAME, "comon-mui-1dvvlpk-profitCalculation")
for div in divs:
    items = div.find_elements(By.XPATH, '//*[@id="profit-calc-date-from-input"]')
    for item in items:
        print("Нашли")
        item.clear()
        item.send_keys("Новое значение")
