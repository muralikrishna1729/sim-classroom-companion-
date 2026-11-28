import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("sim_access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export type User = { id: string; full_name: string; email: string };
export type Classroom = { id: string; school_id: string; name: string; grade_label?: string | null };
export type Assignment = {
  id: string; classroom_id: string; title: string; instructions: string;
  status: string; due_at: string | null; timezone: string;
  recipient_id?: string | null; my_status?: string | null;
};
export type Notification = { id: string; title: string; message: string; read_at?: string | null; created_at: string };

export const authApi = {
  async login(email: string, password: string) {
    const { data } = await api.post<{ access_token: string }>("/auth/login", { email, password });
    localStorage.setItem("sim_access_token", data.access_token);
    return data;
  },
  async register(full_name: string, email: string, password: string) {
    const { data } = await api.post<{ access_token: string; user: User }>("/auth/register", { full_name, email, password });
    localStorage.setItem("sim_access_token", data.access_token);
    return data;
  },
  async me() { return (await api.get<User>("/auth/me")).data; },
  logout() { localStorage.removeItem("sim_access_token"); },
};

export const classroomApi = {
  async list() { return (await api.get<Classroom[]>("/classrooms")).data; },
};

export const assignmentApi = {
  async list(classroomId?: string) {
    return (await api.get<Assignment[]>("/assignments", { params: classroomId ? { classroom_id: classroomId } : {} })).data;
  },
  async create(payload: {
    classroom_id: string; title: string; instructions: string; target_type: "class";
    timezone: string; due_at: string | null;
  }) { return (await api.post("/assignments", payload)).data; },
  async progress(assignmentId: string) {
    return (await api.get(`/assignments/${assignmentId}/progress`)).data;
  },
  async updateProgress(recipientId: string, status: "acknowledged" | "in_progress" | "blocked") {
    return (await api.patch(`/assignments/recipients/${recipientId}/progress`, { status })).data;
  },
};

export const notificationApi = {
  async list() { return (await api.get<{ items: Notification[]; unread_count: number }>("/notifications")).data; },
};

export default api;