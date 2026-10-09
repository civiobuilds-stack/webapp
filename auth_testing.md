# CIVIO BUILD — Auth Testing

## Accounts (seeded)
- Admin/Owner: civiobuilds@gmail.com / CivioAdmin@2026 (role: admin)
- Project Manager: pm@civio.build / CivioPM@2026 (role: project_manager)
- Site Engineer: engineer@civio.build / CivioEng@2026 (role: site_engineer)
- Client: client@civio.build / CivioClient@2026 (role: client)

## Auth = Bearer token in localStorage + Authorization header. Cookies also set.

## API tests
```
curl -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" -d '{"email":"civiobuilds@gmail.com","password":"CivioAdmin@2026"}'
# -> { access_token, user }
curl http://localhost:8001/api/auth/me -H "Authorization: Bearer <token>"
```

## Endpoints
- POST /api/auth/register, /api/auth/login, /api/auth/logout
- GET  /api/auth/me
- Projects: /api/projects (GET/POST), /api/projects/{id} (GET/PUT), /api/projects/{id}/archive
- Users: /api/users (GET admin/pm), POST /api/users (create engineer/client)
- Activities: /api/projects/{id}/activities (GET/POST)
- Progress: /api/progress-updates ...
- Defects: /api/projects/{id}/defects ...
- Files: POST /api/files/upload, GET /api/files/{id}/download
- Notifications: /api/notifications
