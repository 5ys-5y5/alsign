-- Migration: Add calculation column to config_lv2_metric_transform
-- Date: 2025-01-XX
-- Description: Adds calculation column to store Python code for dynamic metric aggregation

ALTER TABLE public.config_lv2_metric_transform 
ADD COLUMN IF NOT EXISTS calculation text NULL;

COMMENT ON COLUMN public.config_lv2_metric_transform.calculation IS 
'Python code string defining the calculation logic. Executed in a restricted namespace for security. 
The code receives quarterly_values (list) and params (dict) as input variables.';


