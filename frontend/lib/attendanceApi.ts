/**
 * Attendance & Workstation Hours API Client
 * Integrated cleanly with FuelFlux Unified Backend
 */

const resolveBackendUrl = (): string => {
  if (process.env.NEXT_PUBLIC_BACKEND_URL) {
    return process.env.NEXT_PUBLIC_BACKEND_URL.replace(/\/+$/, "");
  }
  if (process.env.NEXT_PUBLIC_API_URL) {
    // If NEXT_PUBLIC_API_URL is http://localhost:8000/api/v1, extract root
    return process.env.NEXT_PUBLIC_API_URL.replace(/\/api\/v1\/?$/, "");
  }
  return "http://localhost:8000";
};

export const BACKEND_URL = resolveBackendUrl();

export async function fetchAttendanceAPI(endpoint: string, options: RequestInit = {}) {
  // Routes are mounted under /api on the backend
  const url = `${BACKEND_URL}/api${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });

    if (!response.ok) {
      const errorBody = await response.text();
      let errorMsg = `API Error: ${response.status}`;
      try {
        const errorJson = JSON.parse(errorBody);
        if (errorJson.detail) {
          if (typeof errorJson.detail === "string") {
            errorMsg = errorJson.detail;
          } else if (Array.isArray(errorJson.detail)) {
            errorMsg = errorJson.detail.map((d: any) => `${d.loc?.slice(-1)[0] || "field"}: ${d.msg}`).join(", ");
          }
        }
      } catch {
        if (errorBody) errorMsg = errorBody;
      }
      throw new Error(errorMsg);
    }

    const text = await response.text();
    return text ? JSON.parse(text) : {};
  } catch (err: any) {
    if (err.name === "TypeError" && err.message?.includes("fetch")) {
      throw new Error(`Unable to connect to unified backend server at ${BACKEND_URL}. Ensure the backend is running.`);
    }
    throw err;
  }
}

// =============================================================================
// Attendance Verification APIs
// =============================================================================
export const getAttendance = (date?: string, employee_id?: string) => {
  const params = new URLSearchParams();
  if (date) params.append("date", date);
  if (employee_id) params.append("employee_id", employee_id);
  const q = params.toString();
  return fetchAttendanceAPI(`/attendance${q ? `?${q}` : ""}`);
};

export const manualAttendanceCheckIn = (
  employeeId: string,
  operator: string = "supervisor",
  notes?: string,
  date?: string
) => {
  return fetchAttendanceAPI("/attendance/manual", {
    method: "POST",
    body: JSON.stringify({
      employee_id: employeeId,
      operator,
      notes: notes || "Manual attendance check-in",
      date: date || undefined,
    }),
  });
};

// =============================================================================
// Workstation Presence & Hours APIs
// =============================================================================
export const getWorkstations = () => fetchAttendanceAPI("/workstations");
export const getWorkstation = (id: number) => fetchAttendanceAPI(`/workstations/${id}`);
export const updateWorkstation = (id: number, data: any) =>
  fetchAttendanceAPI(`/workstations/${id}`, { method: "PUT", body: JSON.stringify(data) });

export const updateWorkstationThreshold = (id: number, minutes: number) =>
  fetchAttendanceAPI(`/workstations/${id}/threshold?minutes=${minutes}`, { method: "PUT" });

export const getWorkstationTelemetry = (id: number) => fetchAttendanceAPI(`/workstations/${id}/status`);

export const startWorkstationSession = (
  id: number,
  employeeId: string,
  operator: string = "supervisor",
  shiftName: string = "General Shift",
  validateAttendance: boolean = true
) =>
  fetchAttendanceAPI(`/workstations/${id}/start`, {
    method: "POST",
    body: JSON.stringify({
      employee_id: employeeId,
      operator,
      shift_name: shiftName,
      validate_attendance: validateAttendance,
    }),
  });

export const stopWorkstationSession = (id: number, operator: string = "supervisor") =>
  fetchAttendanceAPI(`/workstations/${id}/stop?operator=${encodeURIComponent(operator)}`, { method: "POST" });

export const getWorkstationIntervals = (id: number, employeeId: string, date?: string) => {
  const params = new URLSearchParams({ employee_id: employeeId });
  if (date) params.append("date", date);
  return fetchAttendanceAPI(`/workstations/${id}/intervals?${params.toString()}`);
};

export const correctWorkstationInterval = (
  id: number,
  data: { interval_id: number; duration_seconds: number; notes: string; operator?: string }
) =>
  fetchAttendanceAPI(`/workstations/${id}/correction`, { method: "POST", body: JSON.stringify(data) });

export const resetWorkstationTodayTime = (id: number, employeeId?: string, date?: string) => {
  const params = new URLSearchParams();
  if (employeeId) params.append("employee_id", employeeId);
  if (date) params.append("date", date);
  const qStr = params.toString();
  return fetchAttendanceAPI(`/workstations/${id}/reset-today${qStr ? `?${qStr}` : ""}`, {
    method: "POST",
  });
};

export const getLiveTracking = (params?: {
  date?: string;
  shift?: string;
  workstation_id?: number;
  employee_id?: string;
  status?: string;
}) => {
  const query = new URLSearchParams();
  if (params?.date) query.append("date", params.date);
  if (params?.shift) query.append("shift", params.shift);
  if (params?.workstation_id) query.append("workstation_id", params.workstation_id.toString());
  if (params?.employee_id) query.append("employee_id", params.employee_id);
  if (params?.status) query.append("status", params.status);
  const qStr = query.toString();
  return fetchAttendanceAPI(`/workstations/tracking/live${qStr ? `?${qStr}` : ""}`);
};

export const getDailyReport = (params?: {
  date?: string;
  shift?: string;
  workstation_id?: number;
}) => {
  const query = new URLSearchParams();
  if (params?.date) query.append("date", params.date);
  if (params?.shift) query.append("shift", params.shift);
  if (params?.workstation_id) query.append("workstation_id", params.workstation_id.toString());
  const qStr = query.toString();
  return fetchAttendanceAPI(`/workstations/reports/daily${qStr ? `?${qStr}` : ""}`);
};

// =============================================================================
// Face Enrollment & Person Roster APIs
// =============================================================================
export const getEmployees = () => fetchAttendanceAPI("/employees");
export const getNextEmployeeId = () => fetchAttendanceAPI("/employees/next-id");
export const getEmployee = (id: string) => fetchAttendanceAPI(`/employees/${id}`);
export const getShifts = () => fetchAttendanceAPI("/employees/shifts");
export const getEnrollmentReport = () => fetchAttendanceAPI("/employees/enrollment-report");
export const syncEmployees = () => fetchAttendanceAPI("/employees/sync", { method: "POST" });

export const createEmployee = async (formData: FormData) => {
  const url = `${BACKEND_URL}/api/employees`;
  const response = await fetch(url, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    let errorMsg = `API Error: ${response.status}`;
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        if (typeof errorJson.detail === "string") {
          errorMsg = errorJson.detail;
        } else if (Array.isArray(errorJson.detail)) {
          errorMsg = errorJson.detail.map((d: any) => `${d.loc?.slice(-1)[0] || "field"}: ${d.msg}`).join(", ");
        }
      }
    } catch {
      const errorText = await response.text().catch(() => "");
      if (errorText) errorMsg = errorText;
    }
    throw new Error(errorMsg);
  }
  return response.json();
};

export const updateEmployee = (id: string | number, data: any) =>
  fetchAttendanceAPI(`/employees/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const deleteEmployee = (id: string) => fetchAttendanceAPI(`/employees/${id}`, { method: "DELETE" });

// =============================================================================
// Camera Management APIs
// =============================================================================
export const startCamera = () => fetchAttendanceAPI("/camera/start", { method: "POST" });
export const stopCamera = () => fetchAttendanceAPI("/camera/stop", { method: "POST" });
export const getCameraStatus = () => fetchAttendanceAPI("/camera/status");

export const startWorkstationCamera = () => fetchAttendanceAPI("/camera/workstation/start", { method: "POST" });
export const stopWorkstationCamera = () => fetchAttendanceAPI("/camera/workstation/stop", { method: "POST" });
export const getWorkstationCameraStatus = () => fetchAttendanceAPI("/camera/workstation/status");

// =============================================================================
// Position Alerts & Absence Threshold APIs
// =============================================================================
export const getAlerts = (params?: {
  employee_id?: string;
  workstation_id?: number;
  status?: string;
  date?: string;
  shift?: string;
  limit?: number;
  offset?: number;
}) => {
  const query = new URLSearchParams();
  if (params?.employee_id) query.append("employee_id", params.employee_id);
  if (params?.workstation_id) query.append("workstation_id", params.workstation_id.toString());
  if (params?.status) query.append("status", params.status);
  if (params?.date) query.append("date", params.date);
  if (params?.shift) query.append("shift", params.shift);
  if (params?.limit) query.append("limit", params.limit.toString());
  if (params?.offset) query.append("offset", params.offset.toString());
  return fetchAttendanceAPI(`/alerts?${query.toString()}`);
};

export const getActiveAlertsCount = () => fetchAttendanceAPI("/alerts/active");

export const getAlertConfig = () => fetchAttendanceAPI("/alerts/config");
export const updateAlertConfig = (thresholdMinutes: number) =>
  fetchAttendanceAPI("/alerts/config", {
    method: "PUT",
    body: JSON.stringify({ threshold_minutes: thresholdMinutes }),
  });

export const acknowledgeAlert = (alertId: number, acknowledgedBy: string = "manager", notes?: string) =>
  fetchAttendanceAPI(`/alerts/${alertId}/acknowledge`, {
    method: "POST",
    body: JSON.stringify({ acknowledged_by: acknowledgedBy, notes }),
  });

export const resolveAlert = (alertId: number, resolvedBy: string = "manager", notes?: string) =>
  fetchAttendanceAPI(`/alerts/${alertId}/resolve`, {
    method: "POST",
    body: JSON.stringify({ resolved_by: resolvedBy, notes }),
  });

export const startWorkstationBreak = (
  workstationId: number,
  breakType: string = "Lunch Break",
  approvedBy: string = "supervisor",
  notes?: string
) =>
  fetchAttendanceAPI(`/workstations/${workstationId}/break/start`, {
    method: "POST",
    body: JSON.stringify({ break_type: breakType, approved_by: approvedBy, notes }),
  });

export const stopWorkstationBreak = (workstationId: number, operator: string = "supervisor") =>
  fetchAttendanceAPI(`/workstations/${workstationId}/break/stop?operator=${encodeURIComponent(operator)}`, {
    method: "POST",
  });
