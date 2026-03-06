import { format, parse } from "date-fns"
import { CalendarIcon } from "lucide-react"

import { cn } from "@/shared/utils"
import { Button } from "@/shared/ui/button"
import { Calendar } from "@/shared/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/ui/popover"

interface DatePickerProps {
  value: string // "YYYY-MM-DD" or ""
  onChange: (value: string) => void
  placeholder?: string
  className?: string
}

export function DatePicker({ value, onChange, placeholder = "Pick a date", className }: DatePickerProps) {
  const date = value ? parse(value, "yyyy-MM-dd", new Date()) : undefined

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            "h-7 justify-start gap-1.5 border-border bg-bg-secondary px-2 py-0.5 text-xs font-normal",
            !value && "text-text-muted",
            value && "text-text-secondary",
            className,
          )}
        >
          <CalendarIcon className="size-3 text-text-muted" />
          {value ? format(date!, "MMM d, yyyy") : placeholder}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={date}
          onSelect={(d) => onChange(d ? format(d, "yyyy-MM-dd") : "")}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  )
}
