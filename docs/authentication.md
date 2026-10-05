# StatusWatch Authentication

## Version

v0.2.0

## Overview

StatusWatch uses JWT Bearer authentication.

Passwords are never stored in plaintext. Passwords are hashed using
Argon2 through pwdlib.

## Endpoints

### Register

POST /auth/register

Creates a new user.

### Login

POST /auth/login

Authenticates a user and returns an access token.

### Current user

GET /auth/me

Requires:

Authorization: Bearer <token>

## Token

The access token contains the user UUID in the `sub` claim.

Access token lifetime is controlled by:

ACCESS_TOKEN_EXPIRE_MINUTES

## Security

- Passwords are stored only as hashes.
- JWT secrets are provided by environment variables.
- JWT secrets are not committed to Git.
- Production and development use different secrets.
- Authentication errors do not reveal whether a password was incorrect.
- Protected endpoints require a valid Bearer token.

## Database migrations

Apply migrations with:

    alembic upgrade head

Check current revision with:

    alembic current

Check model/migration drift with:

    alembic check

## Consolidação v1.0

JWT_SECRET exige pelo menos 32 caracteres; TTL deve ser positivo. HS256, HS384
e HS512 são permitidos. Tokens precisam de exp/sub/type; inválidos e expirados
retornam 401. Inputs de validação não são ecoados em respostas 422.
