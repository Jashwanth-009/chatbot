import configparser
import logging

logging.basicConfig(level=logging.INFO,filemode='w',filename='logs/config.log',encoding="utf-8",format='%(asctime)s - %(levelname)s - %(message)s')

logging.info("logging successful")

config=configparser.ConfigParser()

config.add_section('path')
config.set('path','pdf_dir',r'./pdfs')

with open(r'C:\Users\Jashwasnth B\OneDrive - TECHTRIAD TEAM INC\Documents\chatbot2\logs\configfile.properties','w') as configfile:
    config.write(configfile)
logging.info("config successful")
