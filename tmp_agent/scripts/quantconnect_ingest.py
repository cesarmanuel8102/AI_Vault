import requests
from qc_results_ingester import ingest_qc_results
# credenciales de QuantConnect obtenidas previamente
credenciales = {'api_key': 'your_api_key', 'secret': 'your_secret'}
response = ingest_qc_results(credenciales)
print(response)