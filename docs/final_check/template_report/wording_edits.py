# (old, new). new == "" means delete the sentence. Quotes are from printed text; citations avoided.
E = [
# p3 opener
("The digitalisation of society has created an increasing demand for secure and trustworthy data sharing", "Secure and trustworthy data sharing is now needed"),
("Although digital transformation creates significant opportunities for collaboration and service innovation, it also introduces a fundamental governance challenge", "Digital services make collaboration easier, but they also raise a governance question"),
("Healthcare represents a particularly important and challenging example of this broader problem.", "Healthcare is a clear example of this problem."),
("These scenarios demonstrate that authorisation is increasingly a distributed governance problem rather than simply a process of authenticating a user and checking a static permission", "In these settings, authorisation is a distributed governance problem, not just a check of a user's login and a static permission"),
("This requires a transition from viewing consent as a static record of permission towards understanding consent as an active and evaluable component of a broader authorisation process", "Consent must therefore be treated as an active, evaluable part of the authorisation process, not as a static record of permission"),
# p4
("Together, these conditions provide the foundation for determining not only whether access has been requested, but whether the resulting authorisation decision has a sufficient basis to be trusted.", "Together, these conditions decide whether an authorisation decision has enough basis to be trusted, not only whether access was requested."),
# p6
("The objective of the review is not simply to identify technologies that can be applied to healthcare data sharing, but to examine", "The review does not only list technologies that can be applied to healthcare data sharing. It examines"),
("This fragmentation creates an important distinction between the availability of security mechanisms and the ability to construct a unified and trustworthy authorisation decision.", "Having the security mechanisms is one thing; combining them into one trustworthy authorisation decision is another."),
# p7-8
("These questions were formulated to ensure that the review remained directly aligned with the technical objectives of the proposed system.", "The questions follow the technical objectives of the proposed system."),
("The inclusion and exclusion criteria were applied consistently throughout the screening process.", ""),
("We carried out all screening, coding, and quality assessment up to the reporting checkpoint", "All screening, coding, and quality assessment up to the reporting checkpoint were carried out by the author"),
("We observed an inverse relation between predicate breadth and assurance strength", "An inverse relation between predicate breadth and assurance strength was observed"),
# p11
("This represents an important area addressed by the proposed framework.", ""),
("Access control becomes more complex when policies must be connected directly to a decentralised consent process.", ""),
# p13
("The reviewed literature demonstrates that existing approaches provide strong solutions for individual dimensions of trustworthy data sharing. These contributions address different layers of the security problem.", "Existing approaches solve single dimensions of trustworthy data sharing, each at a different layer of the security problem."),
# p14
("The comparison indicates that the principal contribution of the proposed research is not the replacement of existing technologies. Rather, it lies in establishing an explicit conceptual relationship among them.", "The comparison shows that the contribution of this research is the explicit relationship it establishes among existing technologies, not their replacement."),
# p15
("Existing literature provides useful foundations for collaborative governance and multi-party verification.", ""),
# p17
("The systematic literature review indicates that substantial research has been conducted on individual mechanisms for securing healthcare data sharing. However, the literature also reveals a significant conceptual and architectural fragmentation", "The systematic literature review shows much work on individual mechanisms for securing healthcare data sharing, but also a conceptual and architectural fragmentation"),
("Recording consent and enforcing trustworthy authorisation represent fundamentally different security problems.", "Recording consent and enforcing trustworthy authorisation are two different security problems."),
("The central gap is therefore not the absence of technologies for recording consent, verifying identity, or restricting data access. Rather, it is the absence of a sufficiently integrated model", "The central gap is the absence of an integrated model"),
("The research therefore conceptualises trust not as a static attribute possessed by a particular entity or technology, but as an emergent property of a verifiable authorisation process.", "In this research, trust is a property of a verifiable authorisation process, not an attribute of one entity or technology."),
("Existing healthcare consent and access-control research provides many of the necessary technological building blocks, but there remains a need for an integrated Trust Computing framework", "Existing healthcare consent and access-control research provides most of the needed technology, but not an integrated Trust Computing framework"),
# p18
("The six questions collectively establish a progression from consent modelling to formal security assurance and empirical validation.", ""),
# p20-21
("The research objectives translate the identified research gap into concrete research and development activities. Each objective represents a research contribution that can be examined conceptually, technically, and, where appropriate, empirically.", "The research objectives turn the research gap into concrete research and development activities."),
("The objective is to establish not only that the prototype can execute valid consent workflows, but also that it behaves correctly when one or more trust conditions are violated.", "The prototype must execute valid consent workflows, and it must also behave correctly when one or more trust conditions are violated."),
("This correspondence ensures that every research question is addressed by a clearly defined research activity and that each objective contributes to the overall development of the proposed trust-oriented authorisation framework.", "Each research question therefore has one research activity, and each objective contributes to the framework."),
# p22
("However, the MVC architecture is not used merely as a conventional software engineering pattern for separating data, interfaces, and application logic. Within the proposed framework, MVC is extended to support a more fundamental separation", "In the proposed framework, MVC does more than separate data, interfaces, and application logic. It is extended to support a separation"),
("Instead, the authorisation decision must emerge from the coordinated evaluation of independently verifiable security conditions.", "Instead, the authorisation decision is the result of evaluating independently verifiable security conditions together."),
("This separation is particularly important in decentralised healthcare data-sharing environments.", ""),
# p24-25
("This distinction is important for the interpretation of the architecture", "For the interpretation of the architecture"),
("Importantly, the framework explicitly separates identity authentication from authorisation.", "The framework separates identity authentication from authorisation."),
# p26-27
("This step addresses an important limitation of identity-based and approval-based access control: a legitimate participant may still request data that fall outside the scope of the patient's consent.", "This step addresses a limitation of identity-based and approval-based access control: a legitimate participant may still request data that fall outside the scope of the patient's consent."),
("The principal contribution of the proposed architecture is not the use of MVC itself, but the way in which MVC is employed to operationalise a trust-oriented authorisation model.", "The contribution of the proposed architecture is the way MVC is used to carry a trust-oriented authorisation model, not the use of MVC itself."),
# p30-32
("The resulting object therefore captures not only the patient's preference but also the evidence required to support subsequent authorisation decisions.", "The resulting object therefore captures the patient's preference and the evidence needed for later authorisation decisions."),
("Existing approaches provide limited treatment of patient consent as a security-bearing and policy-aware authorisation object whose validity depends on coordinated conditions concerning participant identity, authority, collective approval, and contextual policy compliance.", ""),
("The main contribution of RO1 is the transformation of consent from a static permission record into a structured authorisation object. The current result demonstrates that consent can be represented as an evaluable authorisation object rather than as a binary permission.", "The main contribution of RO1 is that consent is represented as an evaluable authorisation object rather than as a binary permission."),
("This distinction is important because the research treats consent as a structured policy-bound object rather than as a simple Boolean permission.", ""),
("This sequence ensures that consent is created only after the relevant identity, authority, purpose, scope, and temporal constraints have been validated.", "Consent is therefore created only after the identity, authority, purpose, scope, and temporal fields have been validated."),
# p34-35
("The purpose of this comparison is to ensure that possession of a valid identity or credential is not automatically interpreted as permission to access healthcare information.", ""),
("This mechanism contributes to the trust-oriented framework by converting identity and authority claims into verifiable evidence.", "This mechanism turns identity and authority claims into verifiable evidence."),
# p37-40
("Decentralised identity systems with multi-party verification have demonstrated the potential to strengthen the process through which identity claims are established or validated", "Decentralised identity systems with multi-party verification strengthen the way identity claims are established and validated"),
("The algorithm also demonstrates why multi-party authorisation is a trust mechanism rather than merely a user-interface feature.", "The algorithm also shows that multi-party authorisation is a trust mechanism, not a user-interface feature."),
# p42-46
("Importantly, both successful and denied decisions should be recorded because a trustworthy authorisation framework requires accountability not only for data that were released but also for access attempts that were rejected.", "Both successful and denied decisions should be recorded, because accountability covers the data that were released and the access attempts that were rejected."),
("This step is particularly important for fine-grained healthcare data access because authorisation to access one category of healthcare information does not imply authorisation to access all categories", "Authorisation to access one category of healthcare information does not imply authorisation to access all categories"),
("This ordering is important because it prevents the system from treating identity validity or collective approval as unrestricted permission.", "This ordering prevents the system from treating identity validity or collective approval as unrestricted permission."),
("The adversarial test set is particularly important because a framework should not only demonstrate that legitimate requests succeed, but also demonstrate resilience against foreseeable attempts to bypass its security controls.", "The adversarial test set matters because a framework must show that legitimate requests succeed and that foreseeable attempts to bypass its security controls fail."),
# p47-49
("Authorisation is not necessarily permanent. A consent that was valid when initially approved may subsequently become invalid due to expiration or revocation. This establishes that consent validity is not a static property. The purpose of RO5 is not simply to add an expiry field.", "Authorisation is not permanent. A consent that was valid when approved can later become invalid through expiration or revocation. RO5 is therefore more than an expiry field."),
("Temporal and lifecycle controls contribute dynamic validity.", ""),
("Trustworthy authorisation is inherently dynamic.", ""),
("Rather than treating authorisation as a one-time event, this approach enables the system to determine whether authorisation remains valid at the precise time an operation is requested.", "The system therefore checks whether authorisation is still valid at the time an operation is requested, instead of treating authorisation as a one-time event."),
("This work will be a major part of the next stage.", ""),
# p50-51
("The formal and empirical components are complementary.", ""),
("The current prototype provides a practical environment for evaluating the trust-oriented authorisation model using synthetic healthcare records.", ""),
("This procedure establishes a distinction between functional correctness and security correctness.", "Functional correctness and security correctness are therefore tested separately."),
# p52
("This process ensures that the consent object contains sufficient information for subsequent identity verification, multi-party authorisation, policy evaluation, and auditability. Consequently, the resulting consent object serves not merely as a record of patient preference, but as a structured authorisation artefact", "The consent object therefore holds the information needed for identity verification, multi-party authorisation, policy evaluation, and auditability. It is a structured authorisation artefact, not only a record of patient preference"),
# p57-58
("An auditor can examine not only whether access occurred, but also whether the requester possessed a valid identity", "An auditor can examine whether access occurred, whether the requester possessed a valid identity"),
("The subsystems represent different interaction responsibilities but share the same architectural principle: none of them independently determines whether access should be granted.", "The subsystems have different responsibilities, and none of them decides on its own whether access should be granted."),
# p60-65
("Consequently, validation does not merely determine whether the final output is ALLOW or DENY; it also determines whether the underlying evidence is consistent with the decision.", "Validation therefore checks the evidence behind each decision as well as the final ALLOW or DENY."),
("The purpose of this analysis is not to conceal unsuccessful cases but to determine whether observed failures represent violations of the intended security properties or limitations that should be addressed in future work.", "The analysis records the unsuccessful cases and classifies each one as a violation of an intended security property or as a limitation to be addressed in the next stage."),
("This confirms that a system may be conceptually correct but incorrectly implemented, or may pass functional tests while failing under invalid or adversarial conditions.", "A design can be correct while its implementation is not, and functional tests alone do not show this."),
("The analysis distinguishes between implementation defects, policy-definition errors, integration problems, incomplete security controls, and limitations of the experimental environment.", "The analysis separates implementation defects from incomplete security controls and from limitations of the test environment."),
("Particular attention will be given to the relationship between the formal security model and the observed behaviour of the implemented system.", "The formal security model will be compared with the observed behaviour of the implemented system."),
("The purpose of this work is not merely to demonstrate that the prototype works under normal conditions, but to establish explicit security properties", "This work establishes explicit security properties"),
("The publication strategy is aligned with the progression of the research.", ""),
("will build upon the foundational trust-oriented authorisation framework established during the current stage and extend the research towards dynamic consent governance, formal security assurance, and comprehensive empirical validation.", "will extend the framework of the current stage to dynamic consent governance, formal security assurance, and a fuller empirical validation."),
]
