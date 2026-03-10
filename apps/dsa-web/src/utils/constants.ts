// 生产环境使用相对路径（同源）；开发环境用空字符串走 Vite 代理 /api -> 8000，避免 405/CORS
export const API_BASE_URL = import.meta.env.VITE_API_URL ?? (import.meta.env.PROD ? '' : '');
