```
project-root/
├── etl/
│   ├── __init__.py
│   ├── fetch/
│   │   ├── __init__.py
│   │   ├── yahoo_fetcher.py
│   │   └── companies.py       
│   ├── transform/
│   │   ├── __init__.py
│   │   ├── json_converter.py
│   │   └── data_cleaner.py
│   └── events/
│       ├── __init__.py
│       ├── deepseek_generator.py
│       └── event_merger.py
│
├── core/
│   ├── __init__.py
│   ├── orchestrator.py       
│   ├── dca_calculator.py
│   ├── portfolio_simulator.py
│   ├── data_provider.py
│   ├── data_validator.py
│   └── table_exporter.py
│
├── config/
│   ├── __init__.py
│   ├── settings.py          
│   ├── logging.conf
│   └── .env.example
│
├── db/                                 
├── web/                                
├── data/                               
├── tests/                              
├── docker/                             
├── scripts/                           
│
├── .gitignore
├── .env                                # не в репозитории
├── requirements.txt
└── README.md
```