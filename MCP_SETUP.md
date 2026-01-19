# MCP 서버 설정 가이드

## 설정 파일 위치

Cursor IDE에서 MCP 서버를 설정하려면 다음 위치에 설정 파일을 추가해야 합니다:

### Windows
```
%APPDATA%\Cursor\User\settings.json
```

또는 Cursor 설정에서 직접 추가할 수 있습니다:
1. Cursor 설정 열기 (Ctrl + ,)
2. "MCP Servers" 또는 "Model Context Protocol" 검색
3. 설정 파일에 다음 내용 추가

## 설정 내용

`.cursor-mcp.json` 파일에 포함된 설정을 Cursor의 MCP 설정에 복사하여 사용하세요:

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": [
        "-y",
        "chrome-devtools-mcp@latest"
      ]
    }
  }
}
```

## Supabase MCP 설정

Supabase MCP는 OAuth 토큰이 필요합니다. 환경 변수로 토큰을 제공하고 헤더에 주입하세요.

1. Supabase 대시보드에서 Access Token 발급
2. 환경 변수 설정
   - Windows PowerShell: `setx SUPABASE_ACCESS_TOKEN "<token>"`
   - 현재 세션만: `$env:SUPABASE_ACCESS_TOKEN = "<token>"`
3. MCP 설정에 `Authorization` 헤더 추가

예시:
```json
{
  "mcpServers": {
    "supabase": {
      "type": "http",
      "url": "https://mcp.supabase.com/mcp?project_ref=fgypclaqxonwxlmqdphx",
      "headers": {
        "Authorization": "Bearer ${SUPABASE_ACCESS_TOKEN}"
      }
    }
  }
}
```

## 추가 옵션

필요에 따라 다음 옵션들을 추가할 수 있습니다:

- `--autoConnect`: 이미 실행 중인 Chrome 브라우저에 자동 연결
- `--channel=stable|beta|canary`: Chrome 채널 지정
- `--isolated=true`: 임시 프로필로 격리 실행
- `--headless=true`: 헤드리스 모드 실행

예시:
```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": [
        "-y",
        "chrome-devtools-mcp@latest",
        "--autoConnect",
        "--channel=stable"
      ]
    }
  }
}
```

## 요구사항

- Node.js v20.19 이상 또는 최신 LTS 버전
- Chrome 브라우저 (최신 버전 권장)

## 참고

- `-y` 플래그는 npx가 패키지를 설치할 때 프롬프트 없이 진행하도록 합니다
- `@latest`는 항상 최신 버전을 사용하도록 합니다
