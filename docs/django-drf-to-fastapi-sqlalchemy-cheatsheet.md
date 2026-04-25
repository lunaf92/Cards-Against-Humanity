# Django / DRF to FastAPI / SQLAlchemy Cheat Sheet

This document is a quick reference for translating common Django ORM and Django REST Framework patterns into the FastAPI + SQLAlchemy style used in this project.

## Django ORM to SQLAlchemy

### Basic querying

Django:

```python
user = User.objects.get(id=user_id)
```

SQLAlchemy:

```python
result = await db.execute(select(User).where(User.id == user_id))
user = result.scalar_one()
```

Django:

```python
user = User.objects.filter(id=user_id).first()
```

SQLAlchemy:

```python
result = await db.execute(select(User).where(User.id == user_id))
user = result.scalars().first()
```

Django:

```python
users = User.objects.filter(is_active=True)
```

SQLAlchemy:

```python
result = await db.execute(select(User).where(User.is_active == True))
users = result.scalars().all()
```

### Create

Django:

```python
user = User.objects.create(username="luna", password_hash="...")
```

SQLAlchemy:

```python
user = User(username="luna", password_hash="...")
db.add(user)
await db.commit()
await db.refresh(user)
```

### Update

Django:

```python
user.username = "new_name"
user.save()
```

SQLAlchemy:

```python
user.username = "new_name"
await db.commit()
await db.refresh(user)
```

### Delete

Django:

```python
user.delete()
```

SQLAlchemy:

```python
await db.delete(user)
await db.commit()
```

### Exists

Django:

```python
exists = User.objects.filter(username="luna").exists()
```

SQLAlchemy:

```python
result = await db.execute(select(User.id).where(User.username == "luna").limit(1))
exists = result.scalar_one_or_none() is not None
```

### Count

Django:

```python
count = User.objects.filter(is_active=True).count()
```

SQLAlchemy:

```python
result = await db.execute(
    select(func.count()).select_from(User).where(User.is_active == True)
)
count = result.scalar_one()
```

### Get or 404 pattern

Django:

```python
user = get_object_or_404(User, id=user_id)
```

SQLAlchemy + FastAPI:

```python
result = await db.execute(select(User).where(User.id == user_id))
user = result.scalar_one_or_none()
if user is None:
    raise HTTPException(status_code=404, detail="User not found")
```

### Filtering by multiple fields

Django:

```python
user = User.objects.filter(username=username, email=email).first()
```

SQLAlchemy:

```python
result = await db.execute(
    select(User).where(User.username == username, User.email == email)
)
user = result.scalars().first()
```

### OR conditions

Django:

```python
from django.db.models import Q

user = User.objects.filter(Q(username=value) | Q(email=value)).first()
```

SQLAlchemy:

```python
result = await db.execute(
    select(User).where((User.username == value) | (User.email == value))
)
user = result.scalars().first()
```

### Ordering

Django:

```python
cards = Card.objects.filter(owner=user).order_by("-created_at")
```

SQLAlchemy:

```python
result = await db.execute(
    select(Card)
    .where(Card.owner_id == user.id)
    .order_by(Card.created_at.desc())
)
cards = result.scalars().all()
```

### Pagination

Django:

```python
cards = Card.objects.all()[offset:offset + limit]
```

SQLAlchemy:

```python
result = await db.execute(
    select(Card).offset(offset).limit(limit)
)
cards = result.scalars().all()
```

### Result helpers you will use a lot

When you do:

```python
result = await db.execute(select(User).where(...))
```

Common follow-ups are:

- `result.scalar_one()`
  - exactly one row expected
  - raises if zero or many
- `result.scalar_one_or_none()`
  - zero or one expected
  - raises if more than one
- `result.scalars().first()`
  - first object or `None`
- `result.scalars().all()`
  - list of objects

### Rule of thumb

- `objects.filter(...)` maps to `select(Model).where(...)`
- `objects.get(...)` maps to `scalar_one()` or `scalar_one_or_none()`
- `objects.create(...)` maps to instantiate + `db.add(...)`
- `save()` maps to `await db.commit()`
- `delete()` maps to `await db.delete(...)` + `commit()`

The key difference is that Django hides the SQL result layer, while SQLAlchemy exposes it more directly.

## DRF to FastAPI

### Core mapping

- DRF `Serializer` maps roughly to Pydantic request/response schemas
- DRF `APIView` or `ViewSet` maps roughly to FastAPI route functions inside routers
- DRF authentication and permissions map roughly to FastAPI dependencies
- DRF business logic that often ends up in serializers or views is usually cleaner in a service layer in FastAPI

### Request validation and response shaping

DRF:

```python
class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
```

FastAPI:

```python
class UserCreate(BaseModel):
    username: str
    password: str
```

In this project, that corresponds to files like:

- [app/schemas/auth.py](app/schemas/auth.py)
- [app/schemas/user.py](app/schemas/user.py)
- [app/schemas/card.py](app/schemas/card.py)

### Views and routers

DRF:

```python
class RegisterView(APIView):
    def post(self, request):
        ...
```

FastAPI:

```python
@router.post("/register")
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    ...
```

In this project, route handlers live in:

- [app/routers/auth.py](app/routers/auth.py)
- [app/routers/users.py](app/routers/users.py)
- [app/routers/cards.py](app/routers/cards.py)

### Authentication and permissions

DRF:

```python
permission_classes = [IsAuthenticated]
```

FastAPI:

```python
current_user: User = Depends(get_current_user)
```

In this project, the auth dependency is defined in:

- [app/core/dependencies.py](app/core/dependencies.py)

### Business logic placement

DRF often encourages business logic to spread between serializers, viewsets, and model methods.

FastAPI tends to be easier to maintain when responsibilities are split like this:

- schemas validate input and shape output
- routers handle HTTP concerns
- services contain business logic
- models define persistence structure

In this project, auth business logic lives in:

- [app/services/auth.py](app/services/auth.py)

### DRF serializer save vs FastAPI service call

DRF:

```python
serializer = RegisterSerializer(data=request.data)
serializer.is_valid(raise_exception=True)
user = serializer.save()
```

FastAPI:

```python
@router.post("/register")
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    user = await AuthService.register_user(
        db, user_data.username, user_data.email or "", user_data.password
    )
    await db.commit()
    ...
```

### Good working mental model

If you come from DRF, this translation is usually the most useful:

- serializer input validation -> Pydantic request model
- serializer output -> Pydantic response model
- APIView / ViewSet action -> router function
- permission_classes -> dependency injection with `Depends(...)`
- serializer.save() or custom view logic -> service function

That is the main architectural shift: FastAPI does not try to bundle validation, persistence, and response shaping into one abstraction as aggressively as DRF does.