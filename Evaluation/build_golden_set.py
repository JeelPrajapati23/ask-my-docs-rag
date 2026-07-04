"""
Build a golden eval set + matching PDF ingestion list from CUAD_v1.json
Output schema matches the RAGAS-style intent-tagged format:

{
  "question": ...,
  "ground_truth": ...,
  "reference_contexts": [...],
  "intent": "FACTUAL" | "ANALYTICAL" | "COMPARATIVE" | "GUARDRAIL",
  "synthesizer": "CUAD" | "HAND_WRITTEN",
  "doc_category": "in_scope" | "cross_doc" | "out_of_scope"
}

Usage:
    python build_golden_set.py /path/to/CUAD_v1.json
"""

import json
import random
from collections import defaultdict

# ---------------- CONFIG ----------------
TARGET_CATEGORIES = [
    "Governing Law",
    "Termination For Convenience",
    "Cap On Liability",
    "Non-Compete",
    "Change Of Control",
    "Audit Rights",
]
PAIRS_PER_CATEGORY = 7
MAX_CONTRACTS = 12
SEED = 42

# hand-written analytical/comparative questions get slotted in manually
# after Tier 1 extraction -- fill these in once you know your final contract set
HAND_WRITTEN_ANALYTICAL = [
  {
    "question": "In the CytoDyn-Vyera License Agreement, if Vyera undergoes a Change of Control with a company that is actively developing a competing HIV treatment, what are Vyera's options to remain compliant?",
    "ground_truth": "Under Section 2.6, Vyera must choose one of three paths within specified windows after the Change of Control closes: (a) within 90 days, enter a binding agreement to sell/divest its rights in the competitive product to a non-affiliated third party (completing the sale within 90 days of that agreement); (b) within 6 months, terminate all development, manufacturing, and commercialization of the competitive product; or (c) terminate the License Agreement itself under Section 11.2(c). Vyera is not considered in breach during a 180-day 'Disposition Period' as long as it is complying with one of these paths.",
    "reference_contexts": ["2.6 Competitive Products. Except as expressly required under this Agreement, Vyera hereby covenants not to Develop, Manufacture, Commercialize or otherwise exploit a Competitive Product in the Territory during the Royalty Term... In the event that Vyera experiences a Change of Control with a Third Party that is actively engaged in the Development, Manufacture or Commercialization of a Competitive Product, then, Vyera shall either: (a) within ninety (90) days after the closing of such Change of Control, enter into a binding written agreement to sell, transfer, assign or divest all of Vyera's and/or its Affiliate's rights in and to such Competitive Product to a non-Affiliate Third Party... or (b) within six (6) months after the closing of such Change of Control, terminate any and all Development, Manufacturing, Commercialization and/or other exploitation of such Competitive Product; or (c) terminate this Agreement in accordance with Section 11.2(c)."],
    "doc_category": "in_scope"
  },
  {
    "question": "Does the Limitation of Liability clause in the CytoDyn-Vyera License Agreement fully shield both parties from all damages, or are there carve-outs?",
    "ground_truth": "The clause is not absolute. Section 13.5 excludes consequential, incidental, special, exemplary, punitive, and indirect damages (including lost profits/revenue) for both parties. However, it explicitly carves out two exceptions: (1) a party's indemnification obligations under Article 13, and (2) any breach of the confidentiality provisions in Article 10. It further clarifies that royalties and milestones owed to CytoDyn from Vyera's commercialization of the product could constitute direct damages recoverable under the arbitration provisions of Article 12, despite the general limitation.",
    "reference_contexts": ["13.5 Limitation of Liability. EXCEPT FOR A PARTY'S OBLIGATIONS SET FORTH IN THIS ARTICLE 13, AND ANY BREACH OF ARTICLE 10 (CONFIDENTIALITY), IN NO EVENT WILL EITHER PARTY BE LIABLE TO THE OTHER PARTY... FOR LOST REVENUE, LOST PROFITS, LOST ROYALTIES, LOST SAVINGS, LOSS OF USE, DAMAGE TO GOODWILL, OR ANY CONSEQUENTIAL, INCIDENTAL, SPECIAL, EXEMPLARY, PUNITIVE OR INDIRECT DAMAGES... FOR CLARITY AND NOTWITHSTANDING THE PROVISIONS OF THE FIRST SENTENCE OF THIS SECTION 13.5, ROYALTIES AND MILESTONES PAYABLE TO CYTODYN IN CONNECTION WITH VYERA'S COMMERCIALIZATION OF LICENSED PRODUCTS IN ACCORDANCE WITH THE TERMS OF THIS AGREEMENT COULD CONSTITUTE DIRECT DAMAGES TO THE EXTENT AWARDED IN ACCORDANCE WITH ARTICLE 12."],
    "doc_category": "in_scope"
  },
  {
    "question": "In the Dova-Valeant Co-Promotion Agreement, is the non-competition obligation mutual, or does it fall more heavily on one party?",
    "ground_truth": "The non-compete is structured as mutual but asymmetric in scope. Section 2.3.1(a) restricts Valeant from competing with the Product in the Territory, with an exception tied to Valeant's Tail Period termination rights. Section 2.3.1(b) separately restricts Dova. Both restrictions carve out products marketed by businesses or persons the redacted text specifies, meaning neither party's restriction is absolute — each has negotiated exceptions, but the specific scope of those exceptions is confidential ([***]) in the filed version.",
    "reference_contexts": ["2.3.1 Non-Competition. (a) [***], neither Valeant nor its Affiliates shall, directly or indirectly, [***] in the Territory other than the Product; provided that if the Agreement is terminated by Dova pursuant to [***], then any Tail Period shall be immediately terminated if either Valeant or any of its Affiliates, directly or indirectly, [***] in the Territory other than the Product during such Tail Period... (a) [***], neither Dova nor is Affiliates shall, directly or indirectly, [***]. Notwithstanding the foregoing, this Section 2.3.1(b) shall not apply to any products marketed, promoted, detailed, offered for sale, or sold by any business (or any portion thereof), other Person, or group of Persons[***]."],
    "doc_category": "in_scope"
  },
  {
    "question": "What audit rights does Valeant have over Dova's financial records in the Co-Promotion Agreement, and are there limits on how often Valeant can exercise them?",
    "ground_truth": "Valeant may inspect and audit Dova's records related to Net Sales and payment obligations, at Valeant's own expense, through a mutually acceptable accounting firm, during normal business hours with reasonable notice. This right is capped at once every 12 months during the Term plus once in the year following the Term, and cannot cover a period already audited — except that Valeant retains the right to conduct additional 'for cause' audits to address significant payment-related problems. If an audit reveals under-reporting or underpayment exceeding a specified threshold, Dova bears the audit costs; otherwise Valeant bears them.",
    "reference_contexts": ["7.2 Valeant Rights. Valeant shall have the right, at its own expense, during normal business hours and upon reasonable prior notice, through certified public accounting firm or other auditor selected by Valeant and reasonably acceptable to Dova... to inspect and audit the applicable records and books maintained by Dova for purposes of verifying Dova's payment obligations within this Agreement... provided, however, that (i) such examination shall not take place more often than once per every twelve (12) months during the Term and once during the one (1) year period following the end of the Term, and (ii) such examination shall not cover a period of time that has previously been audited; provided that Valeant shall have the right to conduct additional 'for cause' audits..."],
    "doc_category": "in_scope"
  },
  {
  "question": "If a party repeatedly fails to satisfy the required service performance standards, under what circumstances does that become an Event of Default, and how do the Agreement's contingency planning provisions affect whether the party will be considered in default during a labour disruption?",
  "ground_truth": "Each party must maintain an on-time performance level of at least 90% of the scheduled delivery time, excluding delays caused by the other party or Force Majeure. Failure to meet this standard in a month constitutes a Monthly Service Failure. If Monthly Performance Failures occur more than three times within any twelve-month period, an Event of Default automatically occurs. However, where a party is unable to perform because of a strike or labour disruption caused by its employees, it must attempt to subcontract the services to operators acceptable to the other party under the same contractual terms. If it successfully continues providing the services through those subcontractors, it is expressly deemed not to be in default under the provision relating to ceasing business, although all other default provisions of the Agreement continue to apply.",
  "reference_contexts": [
    "3.4 Each Party agrees to provide the services outlined above at an on time performance level of no less than ninety percent (90%) of the scheduled delivery time, excluding delays caused by the other Party or events of Force Majeure. Monthly, the performance level shall be measured as set out above. Failure to provide services as set out herein constitutes a Monthly Service Failure.\n\n15.1 In the event a Party is unable to provide the Services as a result of a strike or other labour disruption caused by its employees, it shall attempt to subcontract the Services to another operator or operators, acceptable to the other Party. Such Services shall be provided by such subcontractor/subcontractors on the same terms and conditions herein set out and will be continued to be provided during the period of any such strike or labour disruption... if such Party provides the Services by subcontracting to another operator/operators, then it shall be deemed not to be in default pursuant to paragraph 17.1(c). Notwithstanding same, all other default provisions as set out in paragraph 17 continue to apply.\n\n16.1 In the event that Monthly Performance Failures occur more than three (3) times in any twelve (12) month period, an Event of Default shall have occurred.\n\n17.1 For the purposes of this Agreement, the following shall constitute Events of Default... (c) if it ceases or threatens to cease to carry on its business."
  ],
  "doc_category": "in_scope"
    },
    {
  "question": "How does the Agreement allocate responsibility when freight is lost, damaged, or delayed, including investigation duties, financial liability, indemnification, insurance requirements, and mechanisms for verifying related records?",
  "ground_truth": "A party is responsible for loss, damage, or delay to freight caused by its acts, omissions, or negligence while the freight is in its care, custody, or control, except where the damage results solely from improper packing. The responsible party must immediately notify the other party, investigate the incident, report its findings within thirty days, and bear the investigation costs if it is responsible; otherwise those costs are shared equally. The liable party must compensate the other party for the actual damages, subject to the contractual liability cap owed to customers. Each party must indemnify the other against claims arising from its services, with that indemnity limited by the insurance coverage required under the Agreement. Both parties must maintain specified cargo and liability insurance, name the other party as an additional insured, and maintain supporting books, records, and operational data that may be reviewed or validated through a mutually agreed auditor.",
  "reference_contexts": [
    "6.1 A Party shall be liable to the other for loss, damage or delay to Freight due to its acts or omissions, including its negligence... occurring while Freight is in its care, custody or control... A Party shall not be liable hereunder if the Freight is damaged solely as a result of improper packing.\n\n6.2 A Party shall... immediately notify the other Party... carry out an investigation... within thirty (30) days... report its findings... All costs associated with such investigation shall be the responsibility of such Party if the loss, damage or delay was due to its acts or omissions; otherwise, the costs shall be shared equally.\n\n6.3 A Party shall... pay to the other Party the actual damages... Such liability shall not exceed the other Party's contractual liability to its customers.\n\n8.1 Each Party shall at all times indemnify and hold harmless the other... arising out of or in any way connected with the indemnifying Party's provision of Services under this Agreement.\n\n8.2 Notwithstanding anything contained herein to the contrary, the indemnifying party's liability... shall not exceed the insurance coverage set out in Section 9.0.\n\n9.1 Each Party shall purchase and maintain... cargo liability insurance... automobile... general liability insurance... the other Party shall be named as an additional insured.\n\n14.3 Each Party shall keep accurate books, accounts and records covering all transactions relating to this Agreement... 14.4 Either Party shall have the right to request the other to provide, through an auditor agreed to by the Parties, validation of the information and data referred to herein."
  ],
  "doc_category": "in_scope"
},
{
  "question": "How does the Agreement balance DIALOG's commercialization exclusivity with ENERGOUS' ability to engage other semiconductor suppliers, and under what circumstances can those exclusivity protections cease or be bypassed?",
  "ground_truth": "The Agreement grants DIALOG commercialization exclusivity by preventing ENERGOUS from manufacturing or permitting other semiconductor suppliers to commercially manufacture or sell the Products or Product Die, subject to specified exceptions. ENERGOUS must also use diligent good-faith efforts to promote DIALOG as the preferred supplier. However, ENERGOUS may engage another semiconductor supplier if a customer provides written notice that it does not wish to use DIALOG or one of its affiliates before DIALOG has been engaged, or, if DIALOG has already been engaged, before the Design-In Phase begins. In addition, if DIALOG discontinues sales of a Product after giving the required notice, the exclusivity associated with that Product ceases, unless DIALOG continues selling Product Updates, repackaged Product Dies, or multichip modules based on that Product.",
  "reference_contexts": [
    "2.5(a) ENERGOUS will not, and will not enable any Semiconductor Supplier, to manufacture, have manufactured, offer for sale, sell, import or export the Products or Product Die in commercial volumes, except a Semiconductor Supplier to the Key Customer for use in the Excluded Applications.\n\n2.5(b) ENERGOUS will use its diligent, good faith efforts to promote DIALOG as the preferred supplier of Products and Product Die. However, ENERGOUS is allowed to engage with a Semiconductor Supplier... if either (i) the customer... notifies ENERGOUS or DIALOG in writing... that it does not want to use DIALOG... or (ii) if DIALOG has been engaged with the customer, the customer notifies ENERGOUS or DIALOG in writing prior to commencement of the Design-In Phase that it does not want to use DIALOG... For clarity, ENERGOUS shall not intentionally supply Products... directly or through distribution channels.\n\n7.2 Discontinuation of Sale of Products. If DIALOG decides to discontinue Sales of any Product, it will notify ENERGOUS at least [***] prior to such discontinuance, and following such notification, the exclusivity rights, if any, associated with that Product will cease; provided, however, this provision will not apply in the event that DIALOG continues Sales of Product Updates, repackaged Product Dies or MCMs."
  ],
  "doc_category": "in_scope"
},
{
  "question": "What contractual mechanisms ensure that ENERGOUS provides ongoing commercialization and technical support to DIALOG, and what remedies are available if ENERGOUS fails to satisfy those obligations?",
  "ground_truth": "The Agreement requires ENERGOUS to support commercialization by providing sales training, marketing materials, technical assistance, and information necessary for manufacturing, testing, troubleshooting, marketing, and customer support. ENERGOUS must also work with DIALOG to establish and implement a Quality Plan covering testing, yield management, failure analysis, corrective actions, and warranty responsibilities. These obligations are supported through regular commercialization meetings and ongoing collaboration. If ENERGOUS fails to provide technical support meeting the agreed service level and does not cure the deficiency within twenty days after notice, DIALOG may suspend payment of Service Fees until the required service level is restored. Similarly, if ENERGOUS fails to satisfy its obligations under the Quality Plan and does not remedy the deficiency within thirty days after notice, DIALOG may suspend Service Fee payments until those obligations are fulfilled.",
  "reference_contexts": [
    "4.1(c) ENERGOUS will provide commercially reasonable sales training, material and support to DIALOG's global application, sales and marketing teams and customers.\n\n4.1(d) ENERGOUS will also support DIALOG with an operations and quality plan... relating to quality matters, including testing, yield management, RMA process, failure analysis, corrective action procedure, ECN/PCN process and detailed agreement on mutual rights and responsibilities with respect to quality issues or warranty claims... Both parties will work in good faith to finalize and implement the Quality Plan within 90 days.\n\n4.2 The parties will meet regularly, but at least once each month during the Term... to share technical and commercial information... including market updates, customer progress, technical review, forecasts and initiatives to boost sales.\n\n4.3 ENERGOUS will support DIALOG's engineers... provide any and all information necessary or useful to support manufacture, testing, marketing, Sale, troubleshooting, compatibility analysis, performance tuning, failure analysis and other support... In the event the Technical Support provided by ENERGOUS falls below a mutually agreed service level... and after failure to address such deficiency within a twenty (20) day notice period, DIALOG may suspend the payment of Service Fees... Furthermore, if ENERGOUS fails to meet its obligations under the Quality Plan... after a thirty (30) day notice period, DIALOG may suspend the payment of Service Fees until such obligations are met."
  ],
  "doc_category": "in_scope"
},
    {
  "question": "How does the Agreement allocate ownership, patent prosecution responsibilities, and licensing rights for Program Results, and what happens if ExxonMobil elects not to maintain or pursue a Program Patent?",
  "ground_truth": "The Agreement provides that ExxonMobil exclusively owns all Program Results, including Program Information, Program Patents, and copyrightable works, regardless of which party's personnel created them, and FCE assigns all ownership rights to ExxonMobil. ExxonMobil has the exclusive authority to prepare, file, prosecute, maintain, enforce, or abandon Program Patents, while bearing the associated costs. FCE must cooperate by assigning inventor rights, executing required documents, and assisting with patent prosecution. If ExxonMobil decides not to prosecute, defend, maintain, enforce, or continue a Program Patent, it must notify FCE, which may elect to continue prosecution or maintenance at its own expense, although ownership of the Program Patent remains with ExxonMobil. Despite ExxonMobil's ownership, FCE receives a royalty-free research license to use Program Results for the Program and broader commercial rights for Power Applications and Hydrogen Applications, with the possibility of negotiating additional commercialization rights for Carbon Capture Applications if ExxonMobil decides not to pursue that field.",
  "reference_contexts": [
    "6.01 Ownership of Program Results. ExxonMobil will solely own Program Information, Program Patents, and copyrightable works resulting from the Program (collectively, 'Program Results'), irrespective of whether the Program Results are conceived, created, developed or acquired by employees or other representatives of FCE, ExxonMobil, or both. FCE will assign, and hereby assigns, to ExxonMobil ownership of Program Results.\n\n6.02 Solicitation of Program Patents. ExxonMobil will have the sole responsibility and the exclusive right to prepare, file, prosecute, and maintain Program Patents... The cost of preparing, filing, prosecuting, and maintaining any such patent applications... will be paid in full by ExxonMobil. For Program Patents, if one or more employees or other representatives of FCE are determined to be inventors, then FCE will: (i) render reasonable assistance; (ii) assign its right, title, and interest; and (iii) execute documents required to effect such assignments.\n\n6.04 Solicitation of Program Patents Discretionary. ExxonMobil has the unencumbered right to file or not to file, prosecute, defend, maintain, abandon, or enforce any Program Patent. If ExxonMobil decides not to prosecute, defend, enforce, maintain or decides to abandon any Program Patent, ExxonMobil will provide notice to FCE, and FCE will then have the right, but not the obligation, to prosecute or maintain the Program Patent at its sole expense. The ownership of such Program Patent will remain with ExxonMobil.\n\n7.01 Grants to FCE of Program Results. ExxonMobil grants FCE a worldwide, non-exclusive, royalty-free license to practice Program Results for research and development under the Program and grants additional commercial rights for Power Applications and Hydrogen Applications, with potential negotiated rights for Carbon Capture Applications if ExxonMobil elects not to pursue Generation 2 Technology for that field."
    ],
  "doc_category": "in_scope"
},
    {
  "question": "How do the Agreement's confidentiality obligations, publication restrictions, and publicity provisions collectively regulate the disclosure and external use of Program Information and Background Information throughout the collaboration?",
  "ground_truth": "The Agreement requires FCE to promptly disclose all Program Information to ExxonMobil while keeping Program Information confidential for twenty years and limiting its use to the Program or expressly authorized licenses. Each party must similarly protect the other party's Background Information for the same period and may use it only for the Program or authorized licensed purposes. Confidential information may be disclosed to affiliates, contractors, or sublicensees only if they are bound by equivalent confidentiality obligations, and limited disclosures required by law or for patent filings are permitted subject to specified procedures. Publications containing Program Information require cooperation between the parties, removal of the non-publishing party's Background Information upon request, and may not violate confidentiality or publicity obligations without prior written consent. Public announcements concerning the Agreement, the collaboration, or use of the other party's name, trademarks, or identity also require prior written consent except for limited legal disclosures and agreed promotional uses.",
  "reference_contexts": [
    "4.01 Program Information Disclosure, Confidentiality and Use Restriction. FCE will promptly disclose to ExxonMobil any and all Program Information... FCE agrees to hold Program Information in confidence... for a period commencing on the Effective Date and ending twenty (20) years thereafter. Without ExxonMobil's prior written consent, FCE agrees to use Program Information only for the Program or as authorized in Article 7.\n\n4.02 Background Information Disclosure, Confidentiality and Use Restriction. Each Party will make available its Background Information... Each Party agrees to hold the other Party's Background Information in confidence for twenty (20) years and to use it only for the Program or as authorized in Article 8.\n\n4.06 Disclosure to Affiliates, Contractors, and Sub-licensees. A Receiving Party may disclose Confidential Information to Affiliates, contractors, and permitted sublicensees provided they are bound by confidentiality obligations no less protective than those contained herein.\n\n4.07 Compelled Disclosure... the Receiving Party shall provide prompt notice and disclose only the minimum amount reasonably necessary.\n\n5.01 Publicity. During the Term the Parties agree that they will not disclose to any Non-Affiliated Third Party that they have entered into this Agreement or issue publicity releases concerning the Agreement without prior written consent, except where disclosure is required by law.\n\n5.02 Publications. The Parties agree to cooperate on publications. If a proposed publication contains the non-publishing Party's Background Information, such information will be deleted upon request. No publication violating Article 4 or Paragraph 5.01 is permitted without prior written consent."
    ],
  "doc_category": "in_scope"
},
    {
  "question": "How does the Agreement limit the Franchisee's territorial and operational rights while preserving the Franchisor's ability to compete within the same market, including through other franchisees, institutional facilities, direct sales channels, and major accounts?",
  "ground_truth": "The Agreement authorizes the Franchisee to operate only one franchised restaurant from the approved Premises and limits catering, delivery, advertising, and direct customer solicitation to the designated Delivery/Catering and Advertising Area. However, the Agreement expressly states that this area does not provide any territorial exclusivity or protected market. The Franchisor retains broad rights to establish additional franchised restaurants, operate competing businesses, license other franchisees, serve institutional facilities, sell through retail, internet, supermarkets, mail order, and other distribution channels, advertise within the Franchisee's market, and negotiate or service designated Major Accounts, regardless of any resulting impact on the Franchisee's sales.",
  "reference_contexts": [
    "1.1 Grant of Franchise. We grant you the right... to operate one Restaurant at the Premises... Your rights are limited. You have no right to operate at any other location, sublicense the Proprietary Marks or System, or use them except as expressly authorized.\n\n1.2 Activities of Franchised Business. You may operate only from the Premises... catering and delivery customers only within the Delivery/Catering and Advertising Area... the designation of the Delivery/Catering and Advertising Area does not grant any territorial rights or protections.\n\n1.2.2 You may advertise and directly solicit customers only within the Delivery/Catering and Advertising Area.\n\n1.3 Our Limitations and Our Reserved Rights. The rights granted are not exclusive. We and our affiliates may establish additional franchised businesses, other branded businesses, institutional facility restaurants, sell through supermarkets, internet, mail order and other channels, advertise in your Delivery/Catering and Advertising Area, serve customers residing there, and provide products or services to Major Accounts regardless of any actual or threatened impact on your sales."
    ],
  "doc_category": "in_scope"
},
{
  "question": "What financial obligations does the Franchisee assume throughout the franchise relationship, including recurring fees, payment procedures, consequences of delinquency, and security interests securing those obligations?",
  "ground_truth": "The Franchisee must pay a non-refundable initial franchise fee, weekly royalties equal to six percent of Gross Revenues, required advertising contributions based on Gross Revenues, and all other amounts due under the Agreement. Payments must generally be made electronically, and the Franchisee may not offset or withhold payments based on alleged claims against the Franchisor. Overdue payments accrue contractual interest, repeated late payments trigger escalating late fees, and dishonored payments incur separate administrative charges. In addition, upon request, the Franchisee must grant the Franchisor a first-priority security interest in substantially all assets used in the franchised business, execute financing documents necessary to perfect that interest, and authorize the Franchisor to execute such filings on the Franchisee's behalf if necessary.",
  "reference_contexts": [
    "3.1 Initial Franchise Fee. You must pay an initial franchise fee of $30,000... fully earned when paid and non-refundable.\n\n3.2 Royalty. You must pay a royalty equal to six percent (6%) of Gross Revenues... calculated and paid weekly.\n\n3.3 Advertising Contributions. During applicable periods you must contribute three percent (3%) of Gross Revenues to the Marketing Fund and additional required Regional Fund contributions.\n\n3.5 Due Date for Payment... payments are due by the first day after the end of each Period.\n\n3.6 Method of Payment... payment by wire transfer or electronic debit... you may not set off, deduct, or otherwise withhold payments.\n\n3.7 Delinquency. Overdue amounts accrue interest at 1.5% per month and repeated late payments result in escalating late fees.\n\n3.8 Dishonored Payments. Dishonored payments result in a $100 Dishonored Payment Charge in addition to other remedies.\n\n3.11 Security Agreement. Upon request, you must grant us a first-priority security interest in substantially all assets of the Franchised Business, execute financing statements, and authorize us to execute such filings on your behalf if necessary."
    ],
  "doc_category": "in_scope"
},
{
  "question": "How does the Agreement balance DIALOG's broad commercialization and manufacturing responsibilities with ENERGOUS's continuing control over Product intellectual property, specifications, and future Product Updates, particularly following changes to Products or a Change of Control?",
  "ground_truth": "The Agreement gives DIALOG extensive rights and responsibilities to manufacture, test, market, distribute, and support the Products, relying on ENERGOUS's Documentation, Approved Production Specifications, and Product Specifications. However, ENERGOUS retains ownership of all Product IP, including Product Updates, Mask Sets, Tooling, and related intellectual property. Product Specifications may be modified by ENERGOUS with advance written notice, while Product Updates are automatically incorporated into the Agreement once released to production. Following a Change of Control, only qualifying Product Updates developed within the specified post-acquisition period remain covered, and any Products incorporating such updates become subject to separate commercial terms negotiated in good faith, provided those terms are no less favorable to DIALOG than the corresponding existing Product.",
  "reference_contexts": [
    "Documentation means all information necessary or useful to support DIALOG's authorized manufacture, testing, sale and support of the Products, including Product Specifications, data sheets, software, test plans, Approved Production Specifications, Tooling designs, and all other items reasonably required for manufacture.\n\nProduct IP means (a) all Intellectual Property Rights in and to the Products, including all Product Updates; (b) any other inventions and work products created or developed in connection with research, development or manufacturing efforts relating to the Products; and (c) all Intellectual Property Rights in and to the Mask Sets and Tooling, in each case owned or controlled by ENERGOUS.\n\nProduct Specifications means ENERGOUS' written technical specifications for the Products... All Product Specifications are subject to change with at least one month's prior written notice to DIALOG, provided that the specification in effect at shipment governs warranty purposes.\n\nProduct Updates means any updates, improvements and modifications to the Products, including software updates, silicon modifications, functionality improvements, power or distance enhancements, and regulatory modifications. Product Updates are automatically added to Exhibit A following release to production. Product Updates developed by an acquirer or successor after a Change of Control are included only for the specified period after the Change of Control, and Products incorporating such updates are subject to separate good-faith negotiated terms that are no less favorable to DIALOG than those applicable to the corresponding Product."
    ],
  "doc_category": "in_scope"
},
{
  "question": "How does the Agreement define and allocate responsibility for manufacturing defects, including Epidemic Defects, and what contractual mechanisms are established to enable continued manufacturing and remediation of affected Products?",
  "ground_truth": "The Agreement distinguishes ordinary manufacturing from systemic product failures by defining Epidemic Defects as widespread material defects arising from a common root cause attributable to the Product Specifications or Approved Production Specifications and exceeding specified return thresholds. To ensure manufacturing continuity and corrective action, ENERGOUS must provide DIALOG with extensive Documentation, Deposit Materials, Approved Production Specifications, testing programs, and manufacturing-related information necessary to manufacture Products and correct design bugs or Epidemic Defects. These contractual mechanisms allow DIALOG to continue manufacturing while providing the technical resources required to investigate, reproduce, and remediate systemic defects affecting production.",
  "reference_contexts": [
    "Deposit Materials means all chip level design databases, circuit schematics, test and characterization programs and associated documentation reasonably required to have Products manufactured, or to allow design bugs or Epidemic Defects to be fixed in the Product.\n\nDocumentation includes Product Specifications, Approved Production Specifications, test reports, characterization reports, firmware, software, yield data, test plans, Tooling designs, and all other materials reasonably required for manufacture, assembly and testing of Products.\n\nEpidemic Defects means material defects of any Product resulting from a common root cause solely attributable to the Product Specifications or Approved Production Specifications and resulting in returns exceeding the contractual thresholds during the applicable measurement period. Multiple defects arising from a single common root cause are treated as a single Epidemic Defect for purposes of the Agreement."
    ],
  "doc_category": "in_scope"
},
{
  "question": "How does the Agreement permit each party to use the other party's brand while ensuring that ownership of intellectual property remains unchanged and preventing unauthorized commercial exploitation?",
  "ground_truth": "The Agreement grants each party a non-exclusive, worldwide, non-transferable, revocable, royalty-free license to use the other party's Brand Features solely for carrying out the co-branding arrangement. Although NETTAXI may display, distribute, and create derivative works from SpinRecords.com's Brand Features as necessary for the Agreement, and SpinRecords.com receives corresponding rights regarding NETTAXI's Brand Features, ownership of each party's Brand Features, web pages, and associated intellectual property remains exclusively with the originating party. The licenses therefore facilitate reciprocal branding without transferring ownership or broader commercial rights beyond the purposes of the Agreement.",
  "reference_contexts": [
    "Section 2 requires SpinRecords.com to brand its pages with NETTAXI Brand Features and NETTAXI to brand designated NETTAXI Pages with SpinRecords.com Brand Features, subject to the Statement of Work and specified limitations.\n\nSection 3.1 grants SpinRecords.com a non-exclusive, worldwide, non-transferable, revocable, royalty-free license to use the NETTAXI Brand Features for purposes of the Agreement.\n\nSection 3.2 grants NETTAXI a non-exclusive, worldwide, non-transferable, revocable, royalty-free license to display, distribute, and create derivative works from SpinRecords.com Brand Features as necessary to carry out the Agreement.\n\nSection 3.3 provides that NETTAXI owns all right, title, and interest in the NETTAXI Brand Features, NETTAXI Pages, and related Intellectual Property Rights, excluding SpinRecords.com Brand Features. Section 3.4 similarly provides that SpinRecords.com owns all right, title, and interest in its Brand Features, Pages, and related Intellectual Property Rights, excluding NETTAXI Brand Features."
    ],
  "doc_category": "in_scope"
},
{
  "question": "How do the Agreement's co-branding obligations, marketing commitments, quarterly performance reviews, and Statements of Work collectively govern the parties' ongoing collaboration beyond the initial implementation?",
  "ground_truth": "The Agreement requires each party not only to display the other's Brand Features in accordance with the applicable Statement of Work but also to use commercially reasonable efforts throughout the Agreement to market the other's services and maximize visitor traffic. The parties must periodically review marketing performance on a quarterly basis and agree upon additional promotional activities when necessary. If the parties later decide to undertake services beyond the existing scope, they must negotiate and execute additional Statements of Work, each of which becomes part of the Agreement upon execution. This framework makes the collaboration an evolving commercial relationship governed by ongoing operational review rather than a one-time branding arrangement.",
  "reference_contexts": [
    "Sections 2.1 and 2.2 require reciprocal co-branding of the parties' web pages in accordance with the Statement of Work.\n\nSections 2.3 and 2.4 require both SpinRecords.com and NETTAXI to use reasonable commercial efforts throughout the Agreement to market the other party's Brand Features and maximize visitor traffic, with quarterly reviews of marketing activities and agreement on additional activities if necessary.\n\nSection 2.5 provides that if the parties desire additional services beyond the existing Statement of Work, they will negotiate additional Statements of Work in good faith. Each executed Statement of Work becomes part of the Agreement, multiple Statements of Work may exist simultaneously, and each must be signed by authorized representatives."
    ],
  "doc_category": "in_scope"
},
{
  "question": "How does the Agreement allocate responsibility for development, commercialization, intellectual property, governance, and financial consideration as the collaboration progresses from the initial development phase through AbbVie's exercise of its licensing option?",
  "ground_truth": "The Agreement establishes a staged collaboration in which the parties jointly oversee development through governance committees while Harpoon initially performs defined development activities under the Initial Development Plan. AbbVie receives an option to obtain broader development and commercialization rights, after which responsibilities expand to include post-exercise development, commercialization, licensing, milestone payments, royalties, and ongoing intellectual property management. The Agreement integrates governance, regulatory responsibilities, payment obligations, patent ownership and prosecution, commercialization rights, and audit provisions into a coordinated framework that changes as the option is exercised and the collaboration advances.",
  "reference_contexts": [
    "Article 2 establishes the Joint Governance Committee, Working Groups, and collaboration management structure.\n\nArticle 3 governs the Initial Development Plan, AbbVie Option, post-exercise development activities, supply obligations, expenses, subcontracting, and regulatory matters.\n\nArticle 4 addresses commercialization responsibilities, commercialization diligence, booking of sales, trademarks, and commercial supply.\n\nArticle 5 grants rights to AbbVie and Harpoon, governs sublicensing, co-promotion rights, retained rights, and exclusivity.\n\nArticle 6 establishes upfront payments, milestone payments, royalties, royalty reports, audit rights, and payment procedures.\n\nArticle 7 allocates ownership of intellectual property, patent prosecution, patent enforcement, infringement actions, and product trademarks."
    ],
  "doc_category": "in_scope"
},
{
  "question": "How do the Agreement's confidentiality obligations, publication controls, audit rights, and post-termination provisions collectively protect confidential information and intellectual property throughout and after the collaboration?",
  "ground_truth": "The Agreement protects confidential information through comprehensive confidentiality obligations covering technical, regulatory, commercial, and agreement-related information exchanged before and during the collaboration. Those protections are reinforced by restrictions on public announcements, publications, permitted disclosures, and use of the parties' names. Financial compliance is supported through contractual audit rights and related dispute procedures, while post-termination provisions govern the return of confidential information, survival of confidentiality obligations, the treatment of intellectual property, and the continuing rights and obligations that remain effective after termination. Together, these provisions ensure that sensitive information remains protected throughout the collaboration and after its conclusion.",
  "reference_contexts": [
    "Article 6 includes audit rights, audit dispute procedures, confidentiality relating to financial information, and payment record obligations.\n\nArticle 9 defines Product Information and Confidential Information, establishes confidentiality obligations, permitted disclosures, restrictions on use of names, public announcements, publications, return of confidential information, and survival of confidentiality obligations.\n\nArticle 12 contains detailed termination provisions, including accrued rights, surviving obligations, reversion rights, termination effects, and continuing obligations following termination.\n\nThe definition of Confidential Information includes technical, regulatory, business, agreement-related, Licensed Compound, Licensed Product, Regulatory Documentation, and other information disclosed before, on, or after the Effective Date, together with special treatment of Joint Know-How and Regulatory Documentation."
    ],
  "doc_category": "in_scope"
}

]

HAND_WRITTEN_COMPARATIVE = [
    # {
    #   "question": "Compare the termination notice periods in Contract A vs Contract B.",
    #   "ground_truth": "<you write this>",
    #   "reference_contexts": ["<clause from A>", "<clause from B>"],
    #   "doc_category": "cross_doc",
    # },
]

# out-of-scope questions -- designed to have NO answer in your corpus.
# ground_truth is always the refusal string; reference_contexts always empty.
GUARDRAIL_QUESTIONS = [
    "What EPA environmental impact assessments and NEPA compliance steps must the strategic alliance parties satisfy before commencing operations?",
    "What is the current market capitalization of either party to this agreement?",
    "Does this contract comply with GDPR Article 17 right-to-erasure requirements?",
    "What was the stock price movement of the parent company on the day this agreement was signed?",
    "What OSHA workplace safety certifications are required under this agreement?",
    "What is the CEO's personal liability under securities fraud statutes for this deal?",
]

REFUSAL_TEXT = "I cannot answer this based on the provided documents. No relevant context was found."

random.seed(SEED)


def load_cuad(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_candidates(data):
    by_category = defaultdict(list)
    for contract in data["data"]:
        title = contract["title"]
        for para in contract["paragraphs"]:
            context = para["context"]
            for qa in para["qas"]:
                if qa.get("is_impossible", False) or not qa["answers"]:
                    continue
                # exact match against the quoted category tag in the question,
                # not a loose substring match against the whole question text
                # (avoids "Non-Compete" false-matching "Competitive Restriction Exception")
                matched_cat = None
                q_text = qa["question"]
                for cat in TARGET_CATEGORIES:
                    if f'"{cat}"' in q_text:
                        matched_cat = cat
                        break
                if not matched_cat:
                    continue
                answer_text = qa["answers"][0]["text"]
                if len(answer_text.strip()) < 5:
                    continue
                by_category[matched_cat].append({
                    "contract_title": title,
                    "question": qa["question"],
                    "ground_truth": answer_text,
                    "context": context,
                })
    return by_category


def pick_contracts_with_max_overlap(by_category):
    """
    Instead of sampling each category independently (which spreads picks
    across many different contracts), first find contracts that cover the
    MOST target categories, so a small contract set can satisfy multiple
    categories at once.
    """
    contract_categories = defaultdict(set)
    for cat, items in by_category.items():
        for item in items:
            contract_categories[item["contract_title"]].add(cat)

    ranked = sorted(contract_categories.keys(), key=lambda t: -len(contract_categories[t]))
    selected = ranked[:MAX_CONTRACTS]
    return set(selected)


def sample_tier1(by_category):
    selected_contracts = pick_contracts_with_max_overlap(by_category)

    golden = []
    used_contracts = set()
    for cat in TARGET_CATEGORIES:
        candidates = [c for c in by_category.get(cat, []) if c["contract_title"] in selected_contracts]
        if not candidates:
            print(f"[warn] no candidates found for category within selected contracts: {cat}")
            continue
        random.shuffle(candidates)
        picked = candidates[:PAIRS_PER_CATEGORY]
        golden.extend(picked)
        used_contracts.update(p["contract_title"] for p in picked)
    return golden, used_contracts


def cap_contracts(golden, used_contracts):
    coverage = defaultdict(set)
    for item in golden:
        coverage[item["contract_title"]].add(item["question"][:30])
    if len(used_contracts) > MAX_CONTRACTS:
        ranked = sorted(used_contracts, key=lambda t: -len(coverage[t]))
        used_contracts = set(ranked[:MAX_CONTRACTS])
        golden = [g for g in golden if g["contract_title"] in used_contracts]
    return golden, used_contracts


def build_final_dataset(tier1, hand_analytical, hand_comparative, guardrails):
    final = []

    for g in tier1:
        final.append({
            "question": g["question"],
            "ground_truth": g["ground_truth"],
            "reference_contexts": [g["context"]],
            "intent": "FACTUAL",
            "synthesizer": "CUAD",
            "doc_category": "in_scope",
        })

    for h in hand_analytical:
        final.append({
            "question": h["question"],
            "ground_truth": h["ground_truth"],
            "reference_contexts": h.get("reference_contexts", []),
            "intent": "ANALYTICAL",
            "synthesizer": "HAND_WRITTEN",
            "doc_category": h.get("doc_category", "in_scope"),
        })

    for h in hand_comparative:
        final.append({
            "question": h["question"],
            "ground_truth": h["ground_truth"],
            "reference_contexts": h.get("reference_contexts", []),
            "intent": "COMPARATIVE",
            "synthesizer": "HAND_WRITTEN",
            "doc_category": h.get("doc_category", "cross_doc"),
        })

    for q in guardrails:
        final.append({
            "question": q,
            "ground_truth": REFUSAL_TEXT,
            "reference_contexts": [],
            "intent": "GUARDRAIL",
            "synthesizer": "HAND_WRITTEN",
            "doc_category": "out_of_scope",
        })

    return final


def main(json_path):
    data = load_cuad(json_path)
    by_category = extract_candidates(data)
    tier1, used_contracts = sample_tier1(by_category)

    final_dataset = build_final_dataset(
        tier1, HAND_WRITTEN_ANALYTICAL, HAND_WRITTEN_COMPARATIVE, GUARDRAIL_QUESTIONS
    )

    with open("golden_qa_set.json", "w", encoding="utf-8") as f:
        json.dump(final_dataset, f, indent=2, ensure_ascii=False)

    with open("pdf_ingest_list.txt", "w", encoding="utf-8") as f:
        for title in sorted(used_contracts):
            f.write(title + ".pdf\n")

    intent_counts = defaultdict(int)
    for item in final_dataset:
        intent_counts[item["intent"]] += 1

    print("Golden set breakdown:")
    for intent, count in intent_counts.items():
        print(f"  {intent}: {count}")
    print(f"Total: {len(final_dataset)}")
    print(f"Distinct contracts needed: {len(used_contracts)}")
    print("Wrote: golden_qa_set.json, pdf_ingest_list.txt")
    print()
    print("NOTE: HAND_WRITTEN_ANALYTICAL and HAND_WRITTEN_COMPARATIVE are empty templates.")
    print("Fill them in manually once you know your final 18-contract set --")
    print("write ground_truth by reasoning over clauses already extracted in Tier 1.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python build_golden_set.py /path/to/CUAD_v1.json")
        sys.exit(1)
    main(sys.argv[1])