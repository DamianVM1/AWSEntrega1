from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, model_validator
from typing import Any, Optional
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import os, uuid, secrets, time, boto3

app = FastAPI(title="AWS Cloud Foundations - Segunda Entrega")

# ─── Config ───────────────────────────────────────────────────────────────────
DB_HOST        = os.getenv("DB_HOST", "localhost")
DB_PORT        = os.getenv("DB_PORT", "3306")
DB_NAME        = os.getenv("DB_NAME", "sicei")
DB_USER        = os.getenv("DB_USER", "admin")
DB_PASS        = os.getenv("DB_PASS", "password")
S3_BUCKET      = os.getenv("S3_BUCKET", "sicei-bucket")
AWS_REGION     = os.getenv("AWS_REGION", "us-east-1")
SNS_TOPIC_ARN  = os.getenv("SNS_TOPIC_ARN", "")
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "sesiones-alumnos")

# ─── SQLAlchemy ───────────────────────────────────────────────────────────────
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine       = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()

class AlumnoDB(Base):
    __tablename__ = "alumnos"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    nombres       = Column(String(100), nullable=False)
    apellidos     = Column(String(100), nullable=False)
    matricula     = Column(String(50),  nullable=False)
    promedio      = Column(Float,       nullable=False)
    password      = Column(String(255), nullable=False)
    fotoPerfilUrl = Column(String(500), nullable=True)

class ProfesorDB(Base):
    __tablename__ = "profesores"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    numeroEmpleado = Column(String(50),  nullable=False)
    nombres        = Column(String(100), nullable=False)
    apellidos      = Column(String(100), nullable=False)
    horasClase     = Column(Integer,     nullable=False)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ─── AWS clients ──────────────────────────────────────────────────────────────
def get_s3():       return boto3.client("s3",       region_name=AWS_REGION)
def get_sns():      return boto3.client("sns",      region_name=AWS_REGION)
def get_dynamodb(): return boto3.resource("dynamodb", region_name=AWS_REGION)

# ─── Exception handlers ───────────────────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [{"campo": str(e["loc"][-1]), "mensaje": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=400, content={"detail": errors})

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})

# ─── Validadores ──────────────────────────────────────────────────────────────
def validar_string(v: Any, campo: str, errs: list):
    if v is None or not isinstance(v, str) or not v.strip():
        errs.append(f"{campo} debe ser texto no vacío")

def validar_int_positivo(v: Any, campo: str, errs: list):
    if v is None:
        errs.append(f"{campo} es requerido")
    elif isinstance(v, float) or not isinstance(v, int):
        errs.append(f"{campo} debe ser un entero")
    elif v < 0:
        errs.append(f"{campo} debe ser >= 0")

# ─── Modelos Pydantic ─────────────────────────────────────────────────────────
class AlumnoCreate(BaseModel):
    nombres:       str
    apellidos:     str
    matricula:     str
    promedio:      float
    password:      str
    fotoPerfilUrl: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def validar(cls, v):
        errs = []
        validar_string(v.get("nombres"),   "nombres",   errs)
        validar_string(v.get("apellidos"), "apellidos", errs)
        validar_string(v.get("matricula"), "matricula", errs)
        validar_string(v.get("password"),  "password",  errs)
        promedio = v.get("promedio")
        if promedio is None:
            errs.append("promedio es requerido")
        elif not isinstance(promedio, (int, float)):
            errs.append("promedio debe ser un número")
        elif not (0.0 <= float(promedio) <= 10.0):
            errs.append("promedio debe estar entre 0.0 y 10.0")
        if errs:
            raise ValueError("; ".join(errs))
        return v

class AlumnoResponse(BaseModel):
    id:            int
    nombres:       str
    apellidos:     str
    matricula:     str
    promedio:      float
    fotoPerfilUrl: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class ProfesorCreate(BaseModel):
    numeroEmpleado: Any
    nombres:        str
    apellidos:      str
    horasClase:     int

    @model_validator(mode="before")
    @classmethod
    def validar(cls, v):
        errs = []
        ne = v.get("numeroEmpleado")
        if ne is None:
            errs.append("numeroEmpleado es requerido")
        elif isinstance(ne, float) and not ne.is_integer():
            errs.append("numeroEmpleado debe ser texto o entero")
        elif isinstance(ne, str) and not ne.strip():
            errs.append("numeroEmpleado no puede estar vacío")
        validar_string(v.get("nombres"),   "nombres",   errs)
        validar_string(v.get("apellidos"), "apellidos", errs)
        validar_int_positivo(v.get("horasClase"), "horasClase", errs)
        if errs:
            raise ValueError("; ".join(errs))
        return v

class ProfesorResponse(BaseModel):
    id:             int
    numeroEmpleado: str
    nombres:        str
    apellidos:      str
    horasClase:     int
    model_config = ConfigDict(from_attributes=True)

# ─── Alumnos ──────────────────────────────────────────────────────────────────
@app.get("/alumnos", response_model=list[AlumnoResponse])
def get_alumnos(db: Session = Depends(get_db)):
    return db.query(AlumnoDB).all()

@app.get("/alumnos/{id}", response_model=AlumnoResponse)
def get_alumno(id: int, db: Session = Depends(get_db)):
    a = db.query(AlumnoDB).filter(AlumnoDB.id == id).first()
    if not a:
        raise HTTPException(status_code=404, detail=f"Alumno {id} no encontrado")
    return a

@app.post("/alumnos", response_model=AlumnoResponse, status_code=201)
def create_alumno(alumno: AlumnoCreate, db: Session = Depends(get_db)):
    nuevo = AlumnoDB(
        nombres=alumno.nombres, apellidos=alumno.apellidos,
        matricula=alumno.matricula, promedio=alumno.promedio,
        password=alumno.password, fotoPerfilUrl=None
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@app.put("/alumnos/{id}", response_model=AlumnoResponse)
def update_alumno(id: int, datos: AlumnoCreate, db: Session = Depends(get_db)):
    a = db.query(AlumnoDB).filter(AlumnoDB.id == id).first()
    if not a:
        raise HTTPException(status_code=404, detail=f"Alumno {id} no encontrado")
    a.nombres = datos.nombres; a.apellidos = datos.apellidos
    a.matricula = datos.matricula; a.promedio = datos.promedio
    a.password = datos.password
    db.commit(); db.refresh(a)
    return a

@app.delete("/alumnos/{id}")
def delete_alumno(id: int, db: Session = Depends(get_db)):
    a = db.query(AlumnoDB).filter(AlumnoDB.id == id).first()
    if not a:
        raise HTTPException(status_code=404, detail=f"Alumno {id} no encontrado")
    db.delete(a); db.commit()
    return {"mensaje": f"Alumno {id} eliminado"}

# ─── Foto perfil S3 ───────────────────────────────────────────────────────────
@app.post("/alumnos/{id}/fotoPerfil")
async def upload_foto(id: int, foto: UploadFile = File(...), db: Session = Depends(get_db)):
    a = db.query(AlumnoDB).filter(AlumnoDB.id == id).first()
    if not a:
        raise HTTPException(status_code=404, detail=f"Alumno {id} no encontrado")
    s3  = get_s3()
    key = f"fotos/{id}/{uuid.uuid4()}_{foto.filename}"
    contenido = await foto.read()
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=contenido,
                  ContentType=foto.content_type, ACL="public-read")
    url = f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"
    a.fotoPerfilUrl = url
    db.commit(); db.refresh(a)
    return {"fotoPerfilUrl": url}

# ─── Email SNS ────────────────────────────────────────────────────────────────
@app.post("/alumnos/{id}/email")
def send_email(id: int, db: Session = Depends(get_db)):
    a = db.query(AlumnoDB).filter(AlumnoDB.id == id).first()
    if not a:
        raise HTTPException(status_code=404, detail=f"Alumno {id} no encontrado")
    sns = get_sns()
    mensaje = (f"Información del alumno:\n"
               f"Nombre: {a.nombres} {a.apellidos}\n"
               f"Matrícula: {a.matricula}\n"
               f"Promedio: {a.promedio}")
    sns.publish(TopicArn=SNS_TOPIC_ARN, Message=mensaje,
                Subject=f"Calificaciones de {a.nombres} {a.apellidos}")
    return {"mensaje": "Correo enviado correctamente"}

# ─── Sessions DynamoDB ────────────────────────────────────────────────────────
@app.post("/alumnos/{id}/session/login")
def login(id: int, body: dict, db: Session = Depends(get_db)):
    a = db.query(AlumnoDB).filter(AlumnoDB.id == id).first()
    if not a:
        raise HTTPException(status_code=404, detail=f"Alumno {id} no encontrado")
    if body.get("password") != a.password:
        raise HTTPException(status_code=400, detail="Contraseña incorrecta")
    session_string = secrets.token_hex(64)  # 128 caracteres
    table = get_dynamodb().Table(DYNAMODB_TABLE)
    table.put_item(Item={
        "id": str(uuid.uuid4()), "fecha": int(time.time()),
        "alumnoId": id, "active": True, "sessionString": session_string
    })
    return {"sessionString": session_string}

@app.post("/alumnos/{id}/session/verify")
def verify(id: int, body: dict):
    session_string = body.get("sessionString")
    if not session_string:
        raise HTTPException(status_code=400, detail="sessionString requerido")
    table = get_dynamodb().Table(DYNAMODB_TABLE)
    result = table.scan(
        FilterExpression="alumnoId = :aid AND sessionString = :ss",
        ExpressionAttributeValues={":aid": id, ":ss": session_string}
    )
    items = result.get("Items", [])
    if not items or not items[0].get("active"):
        raise HTTPException(status_code=400, detail="Sesión inválida o expirada")
    return {"mensaje": "Sesión válida"}

@app.post("/alumnos/{id}/session/logout")
def logout(id: int, body: dict):
    session_string = body.get("sessionString")
    if not session_string:
        raise HTTPException(status_code=400, detail="sessionString requerido")
    table = get_dynamodb().Table(DYNAMODB_TABLE)
    result = table.scan(
        FilterExpression="alumnoId = :aid AND sessionString = :ss",
        ExpressionAttributeValues={":aid": id, ":ss": session_string}
    )
    items = result.get("Items", [])
    if not items:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    table.update_item(
        Key={"id": items[0]["id"]},
        UpdateExpression="SET active = :val",
        ExpressionAttributeValues={":val": False}
    )
    return {"mensaje": "Sesión cerrada"}

# ─── Profesores ───────────────────────────────────────────────────────────────
@app.get("/profesores", response_model=list[ProfesorResponse])
def get_profesores(db: Session = Depends(get_db)):
    return db.query(ProfesorDB).all()

@app.get("/profesores/{id}", response_model=ProfesorResponse)
def get_profesor(id: int, db: Session = Depends(get_db)):
    p = db.query(ProfesorDB).filter(ProfesorDB.id == id).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Profesor {id} no encontrado")
    return p

@app.post("/profesores", response_model=ProfesorResponse, status_code=201)
def create_profesor(profesor: ProfesorCreate, db: Session = Depends(get_db)):
    nuevo = ProfesorDB(
        numeroEmpleado=str(profesor.numeroEmpleado),
        nombres=profesor.nombres, apellidos=profesor.apellidos,
        horasClase=profesor.horasClase
    )
    db.add(nuevo); db.commit(); db.refresh(nuevo)
    return nuevo

@app.put("/profesores/{id}", response_model=ProfesorResponse)
def update_profesor(id: int, datos: ProfesorCreate, db: Session = Depends(get_db)):
    p = db.query(ProfesorDB).filter(ProfesorDB.id == id).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Profesor {id} no encontrado")
    p.numeroEmpleado = str(datos.numeroEmpleado)
    p.nombres = datos.nombres; p.apellidos = datos.apellidos
    p.horasClase = datos.horasClase
    db.commit(); db.refresh(p)
    return p

@app.delete("/profesores/{id}")
def delete_profesor(id: int, db: Session = Depends(get_db)):
    p = db.query(ProfesorDB).filter(ProfesorDB.id == id).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Profesor {id} no encontrado")
    db.delete(p); db.commit()
    return {"mensaje": f"Profesor {id} eliminado"}
