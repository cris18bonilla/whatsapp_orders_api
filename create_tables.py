from db import engine
import models

print("Creando tablas nuevas...")
models.Base.metadata.create_all(bind=engine)
print("Listo.")
