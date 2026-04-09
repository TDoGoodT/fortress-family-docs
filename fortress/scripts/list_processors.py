"""List Google Document AI processors."""
from google.cloud import documentai
client = documentai.DocumentProcessorServiceClient()
parent = client.common_location_path("fortress-ai-v1", "us")
for p in client.list_processors(parent=parent):
    pid = p.name.split("/")[-1]
    print(f"id={pid} name={p.display_name} type={p.type_} state={p.state.name}")
