'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import {
  UserPlus,
  Trash2,
  Edit2,
  RefreshCw,
  Search,
  ShieldCheck,
  User,
  Upload,
  X,
  Camera,
  Check,
  ArrowLeft,
  Mail,
  Phone,
  Building,
} from 'lucide-react';
import {
  getEmployees,
  getNextEmployeeId,
  getShifts,
  createEmployee,
  deleteEmployee,
  syncEmployees,
  getWorkstations,
} from '@/lib/attendanceApi';
import { toast } from '@/components/feedback/Toast';

export default function FaceEnrollmentPage() {
  const [employees, setEmployees] = useState<any[]>([]);
  const [shifts, setShifts] = useState<any[]>([]);
  const [workstations, setWorkstations] = useState<any[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // New Employee Enrollment Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedPhotos, setSelectedPhotos] = useState<File[]>([]);
  const [photoPreviews, setPhotoPreviews] = useState<string[]>([]);

  const [formData, setFormData] = useState({
    name: '',
    employee_id: 'EMP001',
    email: '',
    phone: '',
    department: 'Operations',
    shift_name: 'General Shift',
    shift_timing: '09:00 - 18:00',
    assigned_workstation_id: '',
  });

  useEffect(() => {
    loadEmployees();
    getShifts().then((data) => setShifts(data || [])).catch(() => {});
    getWorkstations().then((data) => setWorkstations(data || [])).catch(() => {});
  }, []);

  const loadEmployees = async () => {
    setLoading(true);
    try {
      const data = await getEmployees();
      setEmployees(data || []);
    } catch (err: any) {
      toast.error('Failed to load employee face roster', err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenModal = async () => {
    try {
      const nextRes = await getNextEmployeeId().catch(() => null);
      let nextId = nextRes?.next_employee_id;
      if (!nextId) {
        let maxNum = employees.length;
        employees.forEach((emp) => {
          const m = String(emp.employee_id || '').match(/(\d+)/);
          if (m) {
            const n = parseInt(m[1], 10);
            if (n > maxNum) maxNum = n;
          }
        });
        nextId = `EMP${String(maxNum + 1).padStart(3, '0')}`;
      }

      setFormData({
        name: '',
        employee_id: nextId,
        email: '',
        phone: '',
        department: 'Operations',
        shift_name: 'General Shift',
        shift_timing: '09:00 - 18:00',
        assigned_workstation_id: '',
      });
      setSelectedPhotos([]);
      setPhotoPreviews([]);
      setIsModalOpen(true);
    } catch {
      setIsModalOpen(true);
    }
  };

  const handlePhotoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files);
      setSelectedPhotos(files);
      const previews = files.map((f) => URL.createObjectURL(f));
      setPhotoPreviews(previews);
    }
  };

  const handleSubmitEnrollment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.employee_id) {
      toast.error('Name and Employee ID are required');
      return;
    }
    if (selectedPhotos.length === 0) {
      toast.error('Please upload at least one face photo for recognition embedding');
      return;
    }

    setIsSubmitting(true);
    try {
      const fd = new FormData();
      fd.append('name', formData.name);
      fd.append('employee_id', formData.employee_id);
      if (formData.email) fd.append('email', formData.email);
      if (formData.phone) fd.append('phone', formData.phone);
      if (formData.department) fd.append('department', formData.department);
      if (formData.shift_name) fd.append('shift_name', formData.shift_name);
      if (formData.shift_timing) fd.append('shift_timing', formData.shift_timing);
      if (formData.assigned_workstation_id) {
        fd.append('assigned_workstation_id', formData.assigned_workstation_id);
      }

      selectedPhotos.forEach((photo) => {
        fd.append('photos', photo);
      });

      await createEmployee(fd);
      toast.success(`Face enrolled successfully for ${formData.name} (${formData.employee_id})`);
      setIsModalOpen(false);
      loadEmployees();
    } catch (err: any) {
      toast.error(err.message || 'Face enrollment failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteEmployee = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to remove ${name} and their face embeddings?`)) {
      return;
    }
    try {
      await deleteEmployee(id);
      toast.info(`Removed employee ${name} from face roster`);
      loadEmployees();
    } catch (err: any) {
      toast.error(err.message || 'Failed to delete employee');
    }
  };

  const handleSyncEmbeddings = async () => {
    setSyncing(true);
    try {
      await syncEmployees();
      toast.success('FaceNet embeddings cache refreshed and synchronized');
      loadEmployees();
    } catch (err: any) {
      toast.error('Sync failed', err.message);
    } finally {
      setSyncing(false);
    }
  };

  const filtered = employees.filter((emp) => {
    const q = search.toLowerCase();
    return (
      emp.name?.toLowerCase().includes(q) ||
      emp.employee_id?.toLowerCase().includes(q) ||
      emp.department?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-primary">
            <ShieldCheck className="h-4 w-4" />
            <span>Face Recognition Biometrics</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 mt-1">
            Face Photo Enrollment & Roster
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Register employee facial embeddings (FaceNet 512-dim) for automatic attendance and workstation verification
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <Link
            href="/dashboard/attendance"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-white border border-slate-200 hover:border-primary text-slate-700 hover:text-primary transition-all shadow-xs"
          >
            <ArrowLeft className="h-4 w-4" /> Attendance Check-In
          </Link>

          <button
            onClick={handleSyncEmbeddings}
            disabled={syncing}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-white border border-slate-200 hover:border-primary text-slate-700 hover:text-primary transition-all shadow-xs"
          >
            <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
            {syncing ? 'Re-Syncing...' : 'Re-Sync Embeddings'}
          </button>

          <button
            onClick={handleOpenModal}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-primary hover:bg-primary-hover text-white shadow-brand transition-all cursor-pointer"
          >
            <UserPlus className="h-4 w-4" /> Enroll New Face
          </button>
        </div>
      </div>

      {/* Roster Controls */}
      <div className="bg-white rounded-2xl p-4 border border-slate-100 shadow-card flex items-center justify-between gap-3">
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search enrolled faces..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-xl border border-slate-200 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-primary transition-all"
          />
        </div>
        <span className="text-xs text-slate-500 font-medium">
          {filtered.length} employees enrolled
        </span>
      </div>

      {/* Enrolled Faces Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {loading && employees.length === 0 ? (
          <div className="col-span-full py-16 text-center text-slate-400">
            <RefreshCw className="h-8 w-8 animate-spin text-primary mx-auto mb-2" />
            <span>Loading enrolled face profiles...</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="col-span-full py-16 text-center text-slate-400">
            <User className="h-10 w-10 text-slate-300 mx-auto mb-2" />
            <span className="font-medium text-slate-600">No enrolled employees found</span>
          </div>
        ) : (
          filtered.map((emp) => (
            <div
              key={emp.employee_id}
              className="bg-white rounded-2xl p-5 border border-slate-100 shadow-card hover:shadow-md transition-all flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="h-12 w-12 rounded-xl bg-orange-50 text-primary font-bold text-base flex items-center justify-center border border-orange-100">
                    {emp.name?.charAt(0)?.toUpperCase() || 'E'}
                  </div>
                  <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-lg bg-slate-100 text-slate-700">
                    {emp.employee_id}
                  </span>
                </div>

                <h3 className="font-bold text-slate-900 text-base">{emp.name}</h3>
                <span className="inline-block mt-0.5 text-xs text-slate-500 font-medium">
                  {emp.department || 'Operations'}
                </span>

                <div className="mt-3 pt-3 border-t border-slate-100 space-y-1.5 text-xs text-slate-600">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Shift:</span>
                    <span className="font-medium text-slate-800">
                      {emp.shift_name || 'General Shift'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Timing:</span>
                    <span className="font-mono text-slate-700">
                      {emp.shift_timing || '09:00 - 18:00'}
                    </span>
                  </div>
                  {emp.assigned_workstation_id && (
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Workstation:</span>
                      <span className="font-semibold text-primary">
                        Station #{emp.assigned_workstation_id}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600">
                  <Check className="h-3 w-3" /> Embeddings Ready
                </span>
                <button
                  onClick={() => handleDeleteEmployee(emp.employee_id, emp.name)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                  title="Remove enrollment"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* New Face Enrollment Modal */}
      <AnimatePresence>
        {isModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsModalOpen(false)}
              className="absolute inset-0 bg-slate-900/40 backdrop-blur-xs"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 15 }}
              className="relative w-full max-w-lg bg-white rounded-2xl p-6 shadow-2xl border border-slate-100 z-10 max-h-[90vh] overflow-y-auto"
            >
              <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
                <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                  <UserPlus className="h-5 w-5 text-primary" /> Enroll New Employee Face
                </h3>
                <button
                  onClick={() => setIsModalOpen(false)}
                  className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <form onSubmit={handleSubmitEnrollment} className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-semibold text-slate-700 mb-1 block">Full Name</label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      required
                      placeholder="e.g. Rahul Sharma"
                      className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-slate-700 mb-1 block">
                      Employee ID (Auto)
                    </label>
                    <input
                      type="text"
                      value={formData.employee_id}
                      onChange={(e) => setFormData({ ...formData, employee_id: e.target.value })}
                      required
                      className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-sm bg-slate-50 font-mono font-bold text-slate-900 focus:outline-none focus:border-primary"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-semibold text-slate-700 mb-1 block">Department</label>
                    <input
                      type="text"
                      value={formData.department}
                      onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                      placeholder="Operations"
                      className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-slate-700 mb-1 block">Working Shift</label>
                    <select
                      value={formData.shift_name}
                      onChange={(e) => setFormData({ ...formData, shift_name: e.target.value })}
                      className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                    >
                      <option value="General Shift">General Shift (09:00 - 18:00)</option>
                      <option value="Day Shift">Day Shift (09:00 - 18:00)</option>
                      <option value="Morning Shift">Morning Shift (06:00 - 14:00)</option>
                      <option value="Evening Shift">Evening Shift (14:00 - 22:00)</option>
                      <option value="Night Shift">Night Shift (20:00 - 05:00)</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-semibold text-slate-700 mb-1 block">Email (Optional)</label>
                    <input
                      type="email"
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      placeholder="rahul@example.com"
                      className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-slate-700 mb-1 block">Phone (Optional)</label>
                    <input
                      type="text"
                      value={formData.phone}
                      onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                      placeholder="+91 9876543210"
                      className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-700 mb-1 block">
                    Assigned Workstation (Optional)
                  </label>
                  <select
                    value={formData.assigned_workstation_id}
                    onChange={(e) =>
                      setFormData({ ...formData, assigned_workstation_id: e.target.value })
                    }
                    className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                  >
                    <option value="">None / Unassigned</option>
                    {workstations.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.code} — {w.name}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Photo Upload Box */}
                <div>
                  <label className="text-xs font-semibold text-slate-700 mb-1 block">
                    Face Photos for Recognition Embedding
                  </label>
                  <div className="border-2 border-dashed border-slate-200 hover:border-primary/60 rounded-xl p-4 text-center cursor-pointer transition-colors bg-slate-50/50">
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={handlePhotoSelect}
                      className="hidden"
                      id="face-photo-input"
                    />
                    <label htmlFor="face-photo-input" className="cursor-pointer block">
                      <Camera className="h-6 w-6 text-slate-400 mx-auto mb-1.5" />
                      <span className="text-xs font-semibold text-primary">
                        Click to select face photos
                      </span>
                      <span className="text-[11px] text-slate-400 block mt-0.5">
                        JPG, PNG, WebP — clear frontal face lighting recommended
                      </span>
                    </label>
                  </div>

                  {photoPreviews.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-2">
                      {photoPreviews.map((src, i) => (
                        <div
                          key={i}
                          className="h-16 w-16 rounded-xl overflow-hidden border border-slate-200 relative"
                        >
                          <img src={src} alt="Preview" className="h-full w-full object-cover" />
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setIsModalOpen(false)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="px-5 py-2 rounded-xl text-xs font-semibold bg-primary hover:bg-primary-hover text-white shadow-brand"
                  >
                    {isSubmitting ? 'Processing Embeddings...' : 'Save & Enroll Face'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
