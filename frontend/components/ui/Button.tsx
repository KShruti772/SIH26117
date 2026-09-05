import React from "react";
import { Button as AntButton } from "antd";
import type { ButtonProps as AntButtonProps } from "antd";
export type ButtonVariant = "primary" | "secondary" | "destructive" | "ghost" | "icon";
interface ButtonProps extends Omit<AntButtonProps, "type" | "icon" | "variant"> { variant?: ButtonVariant; icon?: React.ReactNode; type?: "button" | "submit" | "reset"; }
export default function Button({ children, variant = "secondary", icon, className, type: htmlType, ...props }: ButtonProps) {
  const color = variant === "primary" ? "primary" : variant === "destructive" ? "danger" : undefined;
  const antVariant = variant === "ghost" || variant === "icon" ? "text" : variant === "secondary" ? "outlined" : "solid";
  return <AntButton color={color} variant={antVariant} htmlType={htmlType} icon={icon} className={`aegis-button aegis-button--${variant}${className ? ` ${className}` : ""}`} {...props}>{children}</AntButton>;
}
