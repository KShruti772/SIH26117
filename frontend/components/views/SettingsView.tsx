"use client";

import React, { useState, useEffect } from "react";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography
} from "antd";
import {
  DatabaseOutlined,
  EditOutlined,
  LockOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  TeamOutlined,
  UserOutlined,
  UserSwitchOutlined
} from "@ant-design/icons";
import { useAuth } from "../providers/AuthProvider";
import { authApi, Department } from "../../lib/api/auth";

interface SettingsViewProps {
  passwordForm: { old_password: string; new_password: string; confirm_password: string };
  setPasswordForm: (value: { old_password: string; new_password: string; confirm_password: string }) => void;
  onSubmit: (event?: React.FormEvent | Record<string, unknown>) => void;
  loading: boolean;
  success: string | null;
  error: string | null;
}

export default function SettingsView(props: SettingsViewProps) {
  const { message } = App.useApp();
  const { user, refreshProfile } = useAuth();

  // Departments State
  const [departments, setDepartments] = useState<Department[]>([]);
  const [deptLoading, setDeptLoading] = useState(false);

  // Create Department Modal
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createCode, setCreateCode] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [creatingDept, setCreatingDept] = useState(false);

  // Edit Department Modal
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editDeptId, setEditDeptId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editActive, setEditActive] = useState(true);
  const [editingDept, setEditingDept] = useState(false);

  // Assign User Department
  const [assignUsername, setAssignUsername] = useState("");
  const [assignDeptId, setAssignDeptId] = useState<number | undefined>(undefined);
  const [assigningUser, setAssigningUser] = useState(false);

  const loadDepartments = async () => {
    if (user?.role !== "admin") return;
    setDeptLoading(true);
    try {
      const data = await authApi.listDepartments();
      setDepartments(data);
    } catch {
      // Admin only or backend error
    } finally {
      setDeptLoading(false);
    }
  };

  useEffect(() => {
    loadDepartments();
  }, [user]);

  const handleCreateDepartment = async () => {
    if (!createName.trim() || !createCode.trim()) {
      message.warning("Department name and code are required.");
      return;
    }
    setCreatingDept(true);
    try {
      await authApi.createDepartment({
        name: createName.trim(),
        code: createCode.trim().toUpperCase(),
        description: createDesc.trim() || undefined
      });
      message.success(`Department '${createName}' created.`);
      setIsCreateModalOpen(false);
      setCreateName("");
      setCreateCode("");
      setCreateDesc("");
      loadDepartments();
    } catch (err: any) {
      message.error(err.message || "Failed creating department.");
    } finally {
      setCreatingDept(false);
    }
  };

  const openEditModal = (dept: Department) => {
    setEditDeptId(dept.id);
    setEditName(dept.name);
    setEditDesc(dept.description || "");
    setEditActive(dept.is_active);
    setIsEditModalOpen(true);
  };

  const handleEditDepartment = async () => {
    if (!editDeptId || !editName.trim()) {
      message.warning("Department name is required.");
      return;
    }
    setEditingDept(true);
    try {
      await authApi.updateDepartment(editDeptId, {
        name: editName.trim(),
        description: editDesc.trim() || undefined,
        is_active: editActive
      });
      message.success("Department updated.");
      setIsEditModalOpen(false);
      loadDepartments();
      refreshProfile();
    } catch (err: any) {
      message.error(err.message || "Failed updating department.");
    } finally {
      setEditingDept(false);
    }
  };

  const handleAssignUserDepartment = async () => {
    if (!assignUsername.trim() || !assignDeptId) {
      message.warning("Username and Department selection are required.");
      return;
    }
    setAssigningUser(true);
    try {
      await authApi.updateUserDepartment(assignUsername.trim(), assignDeptId);
      message.success(`Assigned user '${assignUsername}' to department.`);
      setAssignUsername("");
      setAssignDeptId(undefined);
      loadDepartments();
      refreshProfile();
    } catch (err: any) {
      message.error(err.message || "Failed to update user department.");
    } finally {
      setAssigningUser(false);
    }
  };

  const update = (key: keyof SettingsViewProps["passwordForm"], value: string) =>
    props.setPasswordForm({ ...props.passwordForm, [key]: value });

  const policies = [
    "Local inference only",
    "Multi-tenant document access control",
    "Secure document deduplication (Hash match != access granted)",
    "Pre-retrieval vector filtering",
    "Audit ledger with HMAC-SHA256 integrity",
    "Sandbox process isolation"
  ];

  const deptColumns = [
    {
      title: "Code",
      dataIndex: "code",
      key: "code",
      render: (v: string) => <Tag color="blue" className="font-mono font-bold text-xs">{v}</Tag>
    },
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (v: string) => <span className="font-semibold text-slate-200">{v}</span>
    },
    {
      title: "Description",
      dataIndex: "description",
      key: "description",
      render: (v: string) => <span className="text-xs text-slate-400">{v || "—"}</span>
    },
    {
      title: "Users",
      dataIndex: "user_count",
      key: "user_count",
      render: (v: number) => <Tag color="cyan">{v || 0} users</Tag>
    },
    {
      title: "Status",
      dataIndex: "is_active",
      key: "is_active",
      render: (v: boolean) => (
        <Tag color={v ? "success" : "error"} className="text-[10px] font-bold">
          {v ? "ACTIVE" : "INACTIVE"}
        </Tag>
      )
    },
    {
      title: "Action",
      key: "action",
      render: (_: any, r: Department) => (
        <Button
          size="small"
          type="text"
          icon={<EditOutlined />}
          onClick={() => openEditModal(r)}
        >
          Edit
        </Button>
      )
    }
  ];

  return (
    <div className="aegis-view-stack space-y-6">
      <section className="aegis-view-heading flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div>
          <Typography.Title level={2} className="!mb-1 !text-slate-100">
            System & Enterprise Settings
          </Typography.Title>
          <Typography.Paragraph className="!mb-0 text-slate-400 text-sm">
            Review security policies, account credentials, and enterprise department access control.
          </Typography.Paragraph>
        </div>
        <Tag color="success" className="font-mono font-bold px-3 py-1">
          POLICIES ENFORCED
        </Tag>
      </section>

      {/* User Profile Summary */}
      <Card className="aegis-panel-card bg-[#080d1a] border-slate-800">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-full bg-blue-500/20 border border-blue-500/40 flex items-center justify-center text-blue-400">
              <UserOutlined className="text-lg" />
            </div>
            <div>
              <div className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <span>{user?.username || "Authenticated User"}</span>
                <Tag color={user?.role === "admin" ? "magenta" : "blue"} className="font-mono text-[10px] font-bold uppercase">
                  {user?.role || "user"}
                </Tag>
              </div>
              <div className="text-xs text-slate-400 flex items-center gap-1.5 mt-0.5">
                <TeamOutlined className="text-blue-400" />
                <span>Department: </span>
                <strong className="text-slate-200">
                  {user?.department_name || "Unassigned"}
                </strong>
              </div>
            </div>
          </div>
          <div className="text-xs text-slate-500 font-mono">
            Node ID: AEGIS-NODE-01 · Sovereign Mode
          </div>
        </div>
      </Card>

      {/* Admin Department Management Section */}
      {user?.role === "admin" && (
        <Card
          title={
            <div className="flex items-center justify-between w-full">
              <Space>
                <TeamOutlined className="text-blue-400" />
                <span className="text-slate-100">Enterprise Department Management</span>
              </Space>
              <Button
                type="primary"
                size="small"
                icon={<PlusOutlined />}
                onClick={() => setIsCreateModalOpen(true)}
                className="bg-blue-600 font-semibold"
              >
                Create Department
              </Button>
            </div>
          }
          className="aegis-panel-card bg-[#080d1a] border-slate-800"
        >
          <Row gutter={[20, 20]}>
            <Col xs={24} lg={16}>
              <Typography.Text strong className="text-xs text-slate-300 block mb-2">
                Active Organizational Departments ({departments.length})
              </Typography.Text>
              <Table
                rowKey="id"
                size="small"
                loading={deptLoading}
                columns={deptColumns}
                dataSource={departments}
                pagination={false}
                scroll={{ x: 600 }}
              />
            </Col>

            <Col xs={24} lg={8}>
              <div className="p-4 bg-[#050811] border border-slate-800 rounded-lg space-y-3">
                <Typography.Text strong className="text-xs text-slate-200 block flex items-center gap-1.5">
                  <UserSwitchOutlined className="text-indigo-400" />
                  Assign User to Department
                </Typography.Text>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Username</label>
                  <Input
                    placeholder="e.g. operator_john"
                    value={assignUsername}
                    onChange={(e) => setAssignUsername(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Target Department</label>
                  <Select
                    placeholder="Select Department"
                    value={assignDeptId}
                    onChange={(v) => setAssignDeptId(v)}
                    className="w-full"
                    options={departments.map((d) => ({
                      value: d.id,
                      label: `${d.name} (${d.code})`
                    }))}
                  />
                </div>
                <Button
                  type="primary"
                  size="small"
                  loading={assigningUser}
                  onClick={handleAssignUserDepartment}
                  className="bg-indigo-600 font-semibold w-full"
                >
                  Update User Assignment
                </Button>
              </div>
            </Col>
          </Row>
        </Card>
      )}

      {/* Account Security & Node Configuration */}
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title={<><LockOutlined /> Account security</>} className="aegis-panel-card">
            <Form layout="vertical" requiredMark={false} onFinish={props.onSubmit}>
              <Form.Item label="Current password">
                <Input.Password
                  value={props.passwordForm.old_password}
                  onChange={(event) => update("old_password", event.target.value)}
                  autoComplete="current-password"
                />
              </Form.Item>
              <Form.Item label="New password">
                <Input.Password
                  value={props.passwordForm.new_password}
                  onChange={(event) => update("new_password", event.target.value)}
                  autoComplete="new-password"
                />
              </Form.Item>
              <Form.Item label="Confirm new password">
                <Input.Password
                  value={props.passwordForm.confirm_password}
                  onChange={(event) => update("confirm_password", event.target.value)}
                  autoComplete="new-password"
                />
              </Form.Item>
              <Button
                htmlType="submit"
                type="primary"
                loading={props.loading}
                disabled={!props.passwordForm.old_password || !props.passwordForm.new_password}
              >
                Update password
              </Button>
            </Form>
            {props.success && <Alert className="mt-4" type="success" showIcon title={props.success} />}
            {props.error && (
              <Alert
                className="mt-4"
                type="error"
                showIcon
                title="Password update failed"
                description={props.error}
              />
            )}
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <Card title={<><SettingOutlined /> Local node configuration</>} className="aegis-panel-card">
            <Descriptions
              column={1}
              size="small"
              items={[
                { key: "api", label: "API endpoint", children: "http://127.0.0.1:8000" },
                { key: "vector", label: "Vector database", children: "ChromaDB · data/chroma_db (Pre-filtered)" },
                { key: "audit", label: "Audit ledger", children: "SQLite append-only (HMAC-SHA256)" },
                { key: "runtime", label: "Model runtime", children: "Ollama Engine · port 11434" },
                { key: "access", label: "Access Control", children: "Strict Multi-Department ACL & Secure Deduplication" }
              ]}
            />
          </Card>
        </Col>

        <Col span={24}>
          <Card title={<><SafetyCertificateOutlined /> Security policies</>} className="aegis-panel-card">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {policies.map((policy) => (
                <div
                  key={policy}
                  className="flex items-center justify-between gap-4 rounded-lg border border-slate-800 p-4 bg-[#050811]"
                >
                  <div>
                    <Typography.Text strong className="text-slate-200">{policy}</Typography.Text>
                    <div className="mt-1 text-xs text-slate-400">Enforced by the local AEGIS backend engine.</div>
                  </div>
                  <Switch checked disabled checkedChildren="ON" unCheckedChildren="OFF" />
                </div>
              ))}
            </div>
          </Card>
        </Col>

        <Col span={24}>
          <Card title={<><DatabaseOutlined /> Data residency & Sovereignty</>} className="aegis-panel-card">
            <Typography.Paragraph className="!mb-0 text-slate-300">
              Inference, documents, embeddings, audit data, and sandbox activity are processed entirely on-premise. All document access decisions are enforced before vector search execution to prevent cross-department data leakage.
            </Typography.Paragraph>
          </Card>
        </Col>
      </Row>

      {/* Create Department Modal */}
      <Modal
        title={
          <Space>
            <TeamOutlined className="text-blue-400" />
            <span>Create Organizational Department</span>
          </Space>
        }
        open={isCreateModalOpen}
        onCancel={() => setIsCreateModalOpen(false)}
        onOk={handleCreateDepartment}
        confirmLoading={creatingDept}
        okText="Create Department"
        okButtonProps={{ className: "bg-blue-600 font-semibold" }}
      >
        <div className="space-y-4 py-3">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Department Name *
            </label>
            <Input
              placeholder="e.g. Research & Development"
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Department Code *
            </label>
            <Input
              placeholder="e.g. RND"
              value={createCode}
              onChange={(e) => setCreateCode(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Description (Optional)
            </label>
            <Input.TextArea
              rows={3}
              placeholder="Description of department operations and jurisdiction..."
              value={createDesc}
              onChange={(e) => setCreateDesc(e.target.value)}
            />
          </div>
        </div>
      </Modal>

      {/* Edit Department Modal */}
      <Modal
        title={
          <Space>
            <EditOutlined className="text-blue-400" />
            <span>Edit Department</span>
          </Space>
        }
        open={isEditModalOpen}
        onCancel={() => setIsEditModalOpen(false)}
        onOk={handleEditDepartment}
        confirmLoading={editingDept}
        okText="Save Changes"
        okButtonProps={{ className: "bg-blue-600 font-semibold" }}
      >
        <div className="space-y-4 py-3">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Department Name *
            </label>
            <Input
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Description
            </label>
            <Input.TextArea
              rows={3}
              value={editDesc}
              onChange={(e) => setEditDesc(e.target.value)}
            />
          </div>
          <div className="flex items-center justify-between pt-2">
            <span className="text-xs font-semibold text-slate-300">Active Status</span>
            <Switch
              checked={editActive}
              onChange={setEditActive}
              checkedChildren="ACTIVE"
              unCheckedChildren="INACTIVE"
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
