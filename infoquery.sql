SELECT [strategy_id]
      ,min([datetime])
      ,max([datetime])
	  ,strategy.name
	  ,strategy.link_text
  FROM [FinamStrategies].[dbo].[history] as hist
  left join [dbo].[strategies] as strategy on hist.strategy_id=strategy.id
  group by [strategy_id],strategy.name,strategy.link_text
  order by strategy_id