# [API Name] Documentation

> **Version**: [X.Y.Z]
> **Base URL**: `https://api.example.com/v1`
> **Authentication**: [Bearer token / API key / OAuth 2.0]

## Overview

[What this API does, who it's for, key concepts]

## Authentication

[How to authenticate, get API keys, token refresh]

## Endpoints

### `GET /resource`

List all resources.

**Parameters**:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `page` | integer | No | Page number (default: 1) |
| `limit` | integer | No | Items per page (default: 20, max: 100) |

**Response** (`200 OK`):
```json
{
  "data": [...],
  "pagination": {"page": 1, "total": 100}
}
```

### `POST /resource`

Create a new resource.

**Request Body**:
```json
{
  "name": "string (required)",
  "description": "string (optional)"
}
```

**Response** (`201 Created`):
```json
{"id": "uuid", "name": "string", "created_at": "ISO8601"}
```

### `GET /resource/{id}`

Get a single resource.

### `PUT /resource/{id}`

Update a resource.

### `DELETE /resource/{id}`

Delete a resource.

## Error Handling

| Code | Description |
|------|-------------|
| 400 | Bad Request — invalid parameters |
| 401 | Unauthorized — invalid or missing auth |
| 404 | Not Found |
| 429 | Rate Limited — retry after X seconds |
| 500 | Internal Server Error |

## Rate Limiting

[Limits, headers, retry strategy]

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | [Date] | Initial release |
