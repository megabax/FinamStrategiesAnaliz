SELECT [strategy_id]
      ,min([datetime])
      ,max([datetime])
	  ,avg([perc_income_day])
	  ,stdev([perc_income_day])
  FROM [FinamStrategies].[dbo].[history]
  group by [strategy_id]
  order by strategy_id
  --where strategy_id=9