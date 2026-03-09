from db import engine
import models_saas

print("Creando tablas SaaS...")
models_saas.Base.metadata.create_all(bind=engine)
print("Listo. Tablas SaaS creadas.")
