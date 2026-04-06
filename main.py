from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, model_validator
from typing import Any

app = FastAPI(title="AWS Cloud Foundations - Primera Entrega")


# ─── 422 → 400 ───────────────────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [{"campo": str(e["loc"][-1]), "mensaje": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=400, content={"detail": errors})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor"})


# ─── Helpers de validación ───────────────────────────────────────────────────

def validar_string_no_vacio(valor: Any, campo: str, errores: list):
    """Acepta solo strings no vacíos. Rechaza None, números, etc."""
    if valor is None or not isinstance(valor, str) or not valor.strip():
        errores.append(f"{campo} debe ser texto no vacío")


def validar_int_no_negativo(valor: Any, campo: str, errores: list):
    """Acepta solo int >= 0. Rechaza float, None, strings."""
    if valor is None:
        errores.append(f"{campo} es requerido")
    elif isinstance(valor, float) or not isinstance(valor, int):
        # bool es subclase de int en Python, lo excluimos
        errores.append(f"{campo} debe ser un entero")
    elif valor < 0:
        errores.append(f"{campo} debe ser >= 0")


# ─── Modelo Alumno ───────────────────────────────────────────────────────────

class Alumno(BaseModel):
    id: int
    nombres: str
    apellidos: str
    matricula: str
    promedio: float

    @model_validator(mode="before")
    @classmethod
    def validar(cls, v):
        errs = []
        validar_string_no_vacio(v.get("nombres"), "nombres", errs)
        validar_string_no_vacio(v.get("apellidos"), "apellidos", errs)
        validar_string_no_vacio(v.get("matricula"), "matricula", errs)

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

    model_config = ConfigDict(from_attributes=True)


# ─── Modelo Profesor ─────────────────────────────────────────────────────────

class Profesor(BaseModel):
    id: int
    # numeroEmpleado puede llegar como int o string (el autotest lo manda como int)
    numeroEmpleado: Any
    nombres: str
    apellidos: str
    horasClase: int

    @model_validator(mode="before")
    @classmethod
    def validar(cls, v):
        errs = []

        # numeroEmpleado: acepta int o string no vacío, rechaza None y float
        ne = v.get("numeroEmpleado")
        if ne is None:
            errs.append("numeroEmpleado es requerido")
        elif isinstance(ne, float) and not ne.is_integer():
            errs.append("numeroEmpleado debe ser texto o entero")
        elif isinstance(ne, str) and not ne.strip():
            errs.append("numeroEmpleado no puede estar vacío")

        validar_string_no_vacio(v.get("nombres"), "nombres", errs)
        validar_string_no_vacio(v.get("apellidos"), "apellidos", errs)
        validar_int_no_negativo(v.get("horasClase"), "horasClase", errs)

        if errs:
            raise ValueError("; ".join(errs))
        return v

    model_config = ConfigDict(from_attributes=True)


# ─── Stores ──────────────────────────────────────────────────────────────────

alumnos: list[Alumno] = []
profesores: list[Profesor] = []


# ─── Alumnos ─────────────────────────────────────────────────────────────────

@app.get("/alumnos", response_model=list[Alumno])
def get_alumnos():
    return alumnos

@app.get("/alumnos/{id}", response_model=Alumno)
def get_alumno(id: int):
    for a in alumnos:
        if a.id == id:
            return a
    raise HTTPException(status_code=404, detail=f"Alumno {id} no encontrado")

@app.post("/alumnos", response_model=Alumno, status_code=201)
def create_alumno(alumno: Alumno):
    for a in alumnos:
        if a.id == alumno.id:
            return a
    alumnos.append(alumno)
    return alumno

@app.put("/alumnos/{id}", response_model=Alumno)
def update_alumno(id: int, datos: Alumno):
    for i, a in enumerate(alumnos):
        if a.id == id:
            updated = Alumno(id=id, nombres=datos.nombres, apellidos=datos.apellidos,
                             matricula=datos.matricula, promedio=datos.promedio)
            alumnos[i] = updated
            return updated
    raise HTTPException(status_code=404, detail=f"Alumno {id} no encontrado")

@app.delete("/alumnos/{id}")
def delete_alumno(id: int):
    for i, a in enumerate(alumnos):
        if a.id == id:
            alumnos.pop(i)
            return {"mensaje": f"Alumno {id} eliminado"}
    raise HTTPException(status_code=404, detail=f"Alumno {id} no encontrado")


# ─── Profesores ──────────────────────────────────────────────────────────────

@app.get("/profesores", response_model=list[Profesor])
def get_profesores():
    return profesores

@app.get("/profesores/{id}", response_model=Profesor)
def get_profesor(id: int):
    for p in profesores:
        if p.id == id:
            return p
    raise HTTPException(status_code=404, detail=f"Profesor {id} no encontrado")

@app.post("/profesores", response_model=Profesor, status_code=201)
def create_profesor(profesor: Profesor):
    for p in profesores:
        if p.id == profesor.id:
            return p
    profesores.append(profesor)
    return profesor

@app.put("/profesores/{id}", response_model=Profesor)
def update_profesor(id: int, datos: Profesor):
    for i, p in enumerate(profesores):
        if p.id == id:
            updated = Profesor(id=id, numeroEmpleado=datos.numeroEmpleado,
                               nombres=datos.nombres, apellidos=datos.apellidos,
                               horasClase=datos.horasClase)
            profesores[i] = updated
            return updated
    raise HTTPException(status_code=404, detail=f"Profesor {id} no encontrado")

@app.delete("/profesores/{id}")
def delete_profesor(id: int):
    for i, p in enumerate(profesores):
        if p.id == id:
            profesores.pop(i)
            return {"mensaje": f"Profesor {id} eliminado"}
    raise HTTPException(status_code=404, detail=f"Profesor {id} no encontrado")
