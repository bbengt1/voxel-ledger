import { zodResolver } from "@hookform/resolvers/zod";
import {
  FormProvider,
  useForm,
  useFormContext,
  type DefaultValues,
  type FieldValues,
  type SubmitHandler,
  type UseFormReturn,
} from "react-hook-form";
import { type ReactNode } from "react";
import { type ZodType } from "zod";

import { cn } from "@/lib/cn";

export interface FormProps<TValues extends FieldValues> {
  schema: ZodType<TValues>;
  defaultValues: DefaultValues<TValues>;
  onSubmit: SubmitHandler<TValues>;
  children: ReactNode | ((methods: UseFormReturn<TValues>) => ReactNode);
  className?: string;
  id?: string;
}

/**
 * Thin wrapper around react-hook-form + zod. Resolves validation through
 * the supplied zod schema and exposes form methods via FormProvider so
 * children can call `useFormContext()` (or use {@link FormField}).
 */
export function Form<TValues extends FieldValues>({
  schema,
  defaultValues,
  onSubmit,
  children,
  className,
  id,
}: FormProps<TValues>) {
  const methods = useForm<TValues>({
    resolver: zodResolver(schema),
    defaultValues,
    mode: "onBlur",
  });

  return (
    <FormProvider {...methods}>
      <form
        id={id}
        noValidate
        onSubmit={methods.handleSubmit(onSubmit)}
        className={cn("space-y-4", className)}
      >
        {typeof children === "function" ? children(methods) : children}
      </form>
    </FormProvider>
  );
}

export interface FormFieldProps {
  name: string;
  label?: string;
  description?: string;
  children: ReactNode;
  className?: string;
}

/**
 * Wraps a single field with a label, optional helper text, and inline
 * error message. The actual input component (e.g. {@link Input}) should
 * be registered via `useFormContext().register(name)` by the caller.
 */
export function FormField({
  name,
  label,
  description,
  children,
  className,
}: FormFieldProps) {
  const {
    formState: { errors },
  } = useFormContext();
  const error = errors[name];
  const errorMessage =
    typeof error?.message === "string" ? error.message : undefined;
  const describedBy = errorMessage
    ? `${name}-error`
    : description
      ? `${name}-description`
      : undefined;

  return (
    <div className={cn("space-y-1.5", className)}>
      {label ? (
        <label
          htmlFor={name}
          className="text-sm font-medium text-foreground"
        >
          {label}
        </label>
      ) : null}
      <div aria-describedby={describedBy}>{children}</div>
      {description && !errorMessage ? (
        <p id={`${name}-description`} className="text-xs text-muted-foreground">
          {description}
        </p>
      ) : null}
      {errorMessage ? (
        <p
          id={`${name}-error`}
          role="alert"
          className="text-xs text-destructive"
        >
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}
