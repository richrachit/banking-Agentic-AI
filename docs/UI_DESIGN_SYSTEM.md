# UI Design System

The retained interface follows the supplied visual direction: navy rail, pale workspace, blue/green/purple/amber palette, rounded white cards and persona-aware navigation.

The single home page presents three connected feature cards and buttons: Bank Statement Analysis, Income & Employment Verification/Account Aggregator, and Dormant Account & Escheatment. Every button opens a dedicated functional workspace; the same destinations remain available in the left navigation. Approvals are a shared governed workspace. Login roles are Customer, Underwriter, Compliance and Admin. The UI calls the API on port 8001 and stores the local token only in page memory.

Responsive behavior collapses the fixed rail and two-column cards below 850px. Production release requires formal accessibility, content design, browser, security and usability testing.
