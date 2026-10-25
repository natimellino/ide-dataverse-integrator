from pathlib import Path

from dotenv import load_dotenv

# Debe cargarse antes de importar config, que instancia Settings() al importarse
load_dotenv(Path(__file__).parent / ".env.test", override=False)
