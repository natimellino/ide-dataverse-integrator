from easyDataverse import Dataverse

API_TOKEN = "set-api-token"

dv = Dataverse(server_url="http://localhost:8081", api_token=API_TOKEN)
dataset = dv.create_dataset()

# Verificar nombres generados
# dataset.ideBridge.info()
dv.list_metadatablocks()
dataset.ideBridge.info()
