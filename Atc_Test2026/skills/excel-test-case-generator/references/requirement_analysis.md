# Requirement Analysis Guide

## Table of Contents

1. [Requirement Analysis Checklist](#requirement-analysis-checklist)
2. [Test Scenario Identification Patterns](#test-scenario-identification-patterns)
3. [Common Feature Test Scenarios](#common-feature-test-scenarios)
4. [Decision Tree for Test Case Design](#decision-tree-for-test-case-design)

## Requirement Analysis Checklist

When analyzing a requirement or feature description, systematically check the following:

### Functional Requirements

- [ ] **Core Functionality**: What is the main purpose of this feature?
- [ ] **User Actions**: What actions can users perform?
- [ ] **Input Fields**: What data needs to be entered?
- [ ] **Validation Rules**: What are the validation requirements?
- [ ] **Business Logic**: What business rules apply?
- [ ] **Output/Results**: What should happen after the action?
- [ ] **State Changes**: What system states change?

### Non-Functional Requirements

- [ ] **Performance**: Are there performance requirements?
- [ ] **Security**: What security considerations exist?
- [ ] **Usability**: What usability requirements are there?
- [ ] **Compatibility**: Are there compatibility requirements?

### Edge Cases and Boundaries

- [ ] **Input Limits**: Minimum/maximum values, lengths, counts
- [ ] **Empty/Null Values**: How are empty inputs handled?
- [ ] **Special Characters**: How are special characters handled?
- [ ] **Concurrent Operations**: What happens with simultaneous actions?
- [ ] **Error Conditions**: What errors can occur?

### Dependencies and Preconditions

- [ ] **System State**: What system state is required?
- [ ] **User Permissions**: What permissions are needed?
- [ ] **Data Requirements**: What data must exist?
- [ ] **External Dependencies**: What external systems/services are involved?

## Test Scenario Identification Patterns

### Pattern 1: User Flow Analysis

For any user-facing feature, identify:

1. **Happy Path**: The ideal, expected user journey
2. **Alternative Paths**: Other valid ways to complete the task
3. **Error Paths**: What happens when things go wrong
4. **Edge Cases**: Boundary conditions and unusual scenarios

**Example - User Registration:**
- Happy Path: User provides valid info → Account created → Confirmation sent
- Alternative: User registers via social login
- Error Path: Invalid email format → Error message shown
- Edge Case: User tries to register with existing email

### Pattern 2: Input-Output Analysis

For features with inputs, test:

1. **Valid Inputs**: Normal, expected values
2. **Invalid Inputs**: Wrong format, type, or value
3. **Boundary Values**: Min, max, just inside/outside limits
4. **Empty/Null**: Missing or empty values
5. **Special Characters**: Unicode, symbols, SQL/XSS attempts

**Example - Password Field:**
- Valid: 8-20 characters, alphanumeric + special chars
- Invalid: Too short (<8), too long (>20), only letters
- Boundary: Exactly 8 chars, exactly 20 chars, 7 chars, 21 chars
- Empty: No password entered
- Special: SQL injection attempts, XSS scripts

### Pattern 3: State Transition Analysis

For features that change system state:

1. **Initial State**: Starting conditions
2. **Valid Transitions**: Allowed state changes
3. **Invalid Transitions**: Disallowed state changes
4. **State Persistence**: Does state persist correctly?

**Example - Order Status:**
- Initial: Order created (status: "pending")
- Valid: pending → paid → shipped → delivered
- Invalid: Cannot go from "pending" directly to "delivered"
- Persistence: Status saved correctly after each transition

### Pattern 4: Integration Points

For features that interact with other systems:

1. **Successful Integration**: Normal interaction flow
2. **Integration Failures**: What if external system fails?
3. **Timeout Handling**: What if response is slow?
4. **Data Synchronization**: Is data consistent?

**Example - Payment Processing:**
- Success: Payment gateway responds → Transaction recorded
- Failure: Gateway unavailable → Error shown, retry option
- Timeout: No response in 30s → Timeout error, retry
- Sync: Payment status updated in both systems

## Common Feature Test Scenarios

### Authentication/Login Features

**Always test:**
- Valid credentials → Successful login
- Invalid username → Error message
- Invalid password → Error message
- Empty fields → Validation error
- Account locked → Appropriate message
- Session timeout → Re-authentication required
- SQL injection attempts → Security blocked
- XSS attempts → Input sanitized
- Password visibility toggle → Works correctly
- Remember me → Credentials saved/restored

### Form Submission Features

**Always test:**
- All required fields filled → Successful submission
- Missing required fields → Validation errors
- Invalid format → Format error messages
- Field length limits → Enforced correctly
- Special characters → Handled properly
- Duplicate submission → Prevented or handled
- Network failure → Error handling
- Success feedback → User notified

### Data Display Features

**Always test:**
- Data loads correctly → All data visible
- Empty state → Appropriate message shown
- Large datasets → Pagination/loading works
- Search/filter → Results accurate
- Sorting → Data sorted correctly
- Refresh → Data updates
- Error state → Error message displayed

### CRUD Operations

**For Create:**
- Valid data → Record created
- Invalid data → Validation errors
- Duplicate data → Appropriate handling
- Required fields → Enforced

**For Read:**
- Existing record → Data displayed correctly
- Non-existent record → 404/error message
- Permissions → Access control enforced

**For Update:**
- Valid changes → Record updated
- Invalid changes → Validation errors
- Concurrent updates → Conflict handling
- Permissions → Update rights checked

**For Delete:**
- Confirmation → User confirms action
- Successful deletion → Record removed
- Dependencies → Prevented if dependencies exist
- Permissions → Delete rights checked

## Decision Tree for Test Case Design

```
User Request → Analyze Requirement
    │
    ├─ What type of feature?
    │   ├─ Authentication → Test: login, logout, session, security
    │   ├─ Form Input → Test: validation, format, length, special chars
    │   ├─ Data Display → Test: loading, empty state, pagination, search
    │   ├─ CRUD Operation → Test: create, read, update, delete scenarios
    │   └─ Business Process → Test: workflow, state transitions, rules
    │
    ├─ What are the inputs?
    │   ├─ Text fields → Test: length, format, validation, special chars
    │   ├─ Numeric fields → Test: min/max, decimals, negative values
    │   ├─ Date/time → Test: format, range, timezone
    │   ├─ File upload → Test: type, size, format validation
    │   └─ Selection → Test: single/multiple, required, default
    │
    ├─ What are the outputs/results?
    │   ├─ Success → Test: correct result, user feedback, state change
    │   ├─ Error → Test: appropriate messages, error handling
    │   ├─ Data display → Test: accuracy, formatting, completeness
    │   └─ State change → Test: persistence, consistency
    │
    └─ What are the dependencies?
        ├─ User permissions → Test: access control, role-based access
        ├─ System state → Test: preconditions, state requirements
        ├─ External services → Test: integration, failure handling
        └─ Data dependencies → Test: required data exists, relationships
```

## Test Scenario Coverage Matrix

For comprehensive coverage, ensure test cases cover:

| Scenario Type | Description | Examples |
|--------------|-------------|----------|
| **Positive** | Normal, expected flows | Valid login, successful registration |
| **Negative** | Error handling, invalid inputs | Wrong password, invalid email format |
| **Boundary** | Edge cases, limits | Min/max length, first/last item |
| **Security** | Security vulnerabilities | SQL injection, XSS, CSRF |
| **Performance** | Load, stress, timeout | Large dataset, slow network |
| **Usability** | User experience | Error messages, help text, navigation |
| **Integration** | System interactions | API calls, database, external services |
| **Regression** | Existing functionality | Ensure new changes don't break old features |

## Quick Reference: Test Case Count Estimation

As a rule of thumb, for a typical feature:

- **Minimum**: 5-10 test cases (core positive + critical negative)
- **Standard**: 15-25 test cases (comprehensive coverage)
- **Thorough**: 30+ test cases (including edge cases, security, performance)

**Distribution:**
- 30-40% Positive cases
- 30-40% Negative cases
- 15-20% Boundary cases
- 10-15% Security/Integration cases

## Example: Requirement to Test Cases

**Requirement**: "User can reset password by email"

**Analysis:**
1. **Core Functionality**: Password reset via email
2. **User Actions**: Request reset, receive email, click link, enter new password
3. **Inputs**: Email address, new password, confirmation password
4. **Validation**: Email format, password strength, password match
5. **Outputs**: Email sent, reset link, password changed, success message

**Test Scenarios Identified:**
- Positive: Valid email → Email sent → Link works → Password reset
- Negative: Invalid email → Error message
- Negative: Non-existent email → Error message (security consideration)
- Negative: Expired reset link → Error message
- Negative: Weak password → Validation error
- Negative: Password mismatch → Error message
- Boundary: Password at min/max length
- Security: Reset link reuse attempt → Prevented
- Security: SQL injection in email field → Blocked

**Result**: ~10-15 test cases covering all scenarios
