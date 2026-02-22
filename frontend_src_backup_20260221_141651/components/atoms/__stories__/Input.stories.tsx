import type { Meta, StoryObj } from '@storybook/react';
import { Input } from '../Input';
import { MagnifyingGlassIcon } from '@heroicons/react/24/outline';

const meta: Meta<typeof Input> = {
  title: 'Atoms/Input',
  component: Input,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['default', 'error', 'success'],
    },
    size: {
      control: 'select',
      options: ['sm', 'md', 'lg'],
    },
  },
};

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    label: 'Email',
    placeholder: 'Enter your email',
    type: 'email',
  },
};

export const WithError: Story = {
  args: {
    label: 'Password',
    type: 'password',
    error: 'Password must be at least 8 characters',
  },
};

export const WithHelper: Story = {
  args: {
    label: 'Username',
    helperText: 'This will be your public display name',
  },
};

export const WithIcon: Story = {
  args: {
    label: 'Search',
    placeholder: 'Search...',
    leftIcon: <MagnifyingGlassIcon className="w-5 h-5" />,
  },
};

export const Small: Story = {
  args: {
    label: 'Small Input',
    size: 'sm',
  },
};

export const Large: Story = {
  args: {
    label: 'Large Input',
    size: 'lg',
  },
};
