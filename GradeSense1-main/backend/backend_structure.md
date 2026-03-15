# Backend Directory Structure

```
backend/
|   .env
|   .gitignore
|   backend_structure.md
|   check_counts.py
|   check_imports.py
|   check_mongo.py
|   check_mongo_json.py
|   main.py
|   mongo_counts.json
|   mongo_dump.json
|   README.md
|   testt.py
|   test_schema_imports.py
|   .pytest_cache/
|   |   .gitignore
|   |   CACHEDIR.TAG
|   |   README.md
|   |   v/
|   |   |   cache/
|   |   |   |   nodeids
|   app/
|   |   await_search_results.txt
|   |   await_search_utf8.txt
|   |   deps.py
|   |   models.zip
|   |   schemas.zip
|   |   __init__.py
|   |   core/
|   |   |   config.py
|   |   |   database.py
|   |   |   db_config.py
|   |   |   logging_config.py
|   |   |   version.py
|   |   domain/
|   |   |   exam_nodes.py
|   |   infrastructure/
|   |   |   storage/
|   |   |   |   gridfs_storage.py
|   |   layers/
|   |   |   grading_engine.py
|   |   |   resolver.py
|   |   |   __init__.py
|   |   |   ai_structured/
|   |   |   |   alignment_service.py
|   |   |   |   cache.py
|   |   |   |   engine.py
|   |   |   |   extraction_service.py
|   |   |   |   grading_interface.py
|   |   |   |   mark_reasoner.py
|   |   |   |   mark_resolver.py
|   |   |   |   prompts.py
|   |   |   |   retry.py
|   |   |   |   safe_numeric.py
|   |   |   |   schemas.py
|   |   |   |   strict_visual_blueprint.py
|   |   |   |   structure_repair.py
|   |   |   |   structure_validator.py
|   |   |   |   validation.py
|   |   |   |   __init__.py
|   |   |   aws_pipeline/
|   |   |   |   answer_extractor.py
|   |   |   |   answer_mapper.py
|   |   |   |   blueprint_builder.py
|   |   |   |   config.py
|   |   |   |   engine.py
|   |   |   |   grading_engine.py
|   |   |   |   layout_segmentation.py
|   |   |   |   question_identity.py
|   |   |   |   raw_layer.py
|   |   |   |   s3_storage.py
|   |   |   |   textract_client.py
|   |   |   |   text_reconstruction.py
|   |   |   |   __init__.py
|   |   |   college/
|   |   |   |   alignment.py
|   |   |   |   blueprint.py
|   |   |   |   contracts.py
|   |   |   |   engine.py
|   |   |   |   grader.py
|   |   |   |   layout.py
|   |   |   |   normalization.py
|   |   |   |   packet_builder.py
|   |   |   |   prompts.py
|   |   |   |   recovery.py
|   |   |   |   region_ocr.py
|   |   |   |   structuring.py
|   |   |   |   __init__.py
|   |   |   college_v3/
|   |   |   |   anchor_detection.py
|   |   |   |   answer_mapping.py
|   |   |   |   contracts.py
|   |   |   |   engine.py
|   |   |   |   global_span_builder.py
|   |   |   |   grading.py
|   |   |   |   question_blueprint.py
|   |   |   |   vision_ocr.py
|   |   |   |   __init__.py
|   |   |   universal/
|   |   |   |   alignment.py
|   |   |   |   confidence.py
|   |   |   |   continuity.py
|   |   |   |   contracts.py
|   |   |   |   embeddings.py
|   |   |   |   engine.py
|   |   |   |   grader.py
|   |   |   |   ingestion.py
|   |   |   |   layout.py
|   |   |   |   normalization.py
|   |   |   |   ocr.py
|   |   |   |   packet_builder.py
|   |   |   |   question_detection.py
|   |   |   |   recovery.py
|   |   |   |   region_ocr.py
|   |   |   |   structuring.py
|   |   |   |   __init__.py
|   |   |   upsc/
|   |   |   |   policy.py
|   |   |   |   prompts.py
|   |   |   |   __init__.py
|   |   |   visual_entities/
|   |   |   |   extractor.py
|   |   |   |   __init__.py
|   |   middleware/
|   |   |   cors.py
|   |   |   metrics.py
|   |   models/
|   |   |   admin.py
|   |   |   analytics.py
|   |   |   batch.py
|   |   |   exam.py
|   |   |   feedback.py
|   |   |   reevaluation.py
|   |   |   subject.py
|   |   |   submission.py
|   |   |   user.py
|   |   |   __init__.py
|   |   pipeline_schemas/
|   |   |   __init__.py
|   |   |   blueprint/
|   |   |   |   question_node.py
|   |   |   |   sub_question_node.py
|   |   |   |   __init__.py
|   |   prompts/
|   |   |   extraction_prompts.yaml
|   |   |   prompt_manager.py
|   |   routes/
|   |   |   admin.py
|   |   |   analytics.py
|   |   |   auth.py
|   |   |   batches.py
|   |   |   debug.py
|   |   |   exams.py
|   |   |   feedback.py
|   |   |   grading.py
|   |   |   health.py
|   |   |   notifications.py
|   |   |   re_evaluations.py
|   |   |   search.py
|   |   |   students.py
|   |   |   student_portal.py
|   |   |   subjects.py
|   |   |   submissions.py
|   |   |   system.py
|   |   |   universal.py
|   |   |   uploads.py
|   |   |   __init__.py
|   |   schemas/
|   |   |   ai_outputs.py
|   |   |   __init__.py
|   |   |   admin/
|   |   |   |   publish_results_request.py
|   |   |   |   user_status_update.py
|   |   |   annotation/
|   |   |   |   annotation_data.py
|   |   |   |   __init__.py
|   |   |   auth/
|   |   |   |   login_request.py
|   |   |   |   register_request.py
|   |   |   |   set_password_request.py
|   |   |   exam/
|   |   |   |   exam_create.py
|   |   |   |   student_exam_create.py
|   |   |   |   __init__.py
|   |   |   user/
|   |   |   |   feature_flags.py
|   |   |   |   profile_update.py
|   |   |   |   quotas.py
|   |   |   |   user_create.py
|   |   services/
|   |   |   analytics.py
|   |   |   annotation.py
|   |   |   answer_sheet_pipeline.py
|   |   |   background.py
|   |   |   blueprint_enrichment.py
|   |   |   extraction_pipeline.py
|   |   |   file_processing.py
|   |   |   grading_pipeline.py
|   |   |   gridfs_helpers.py
|   |   |   llm.py
|   |   |   llm_config.py
|   |   |   metrics.py
|   |   |   notifications.py
|   |   |   question_mapper.py
|   |   |   score_normalization.py
|   |   |   segmentation.py
|   |   |   simple_pipeline.py
|   |   |   student_detection.py
|   |   |   task_worker.py
|   |   |   __init__.py
|   |   |   extraction/
|   |   |   |   blueprint_generator.py
|   |   |   |   legacy_extraction.py
|   |   |   |   __init__.py
|   |   |   grading/
|   |   |   |   annotation_mapper.py
|   |   |   |   answer_normalizer.py
|   |   |   |   concept_matcher.py
|   |   |   |   context_builder.py
|   |   |   |   legacy_grading.py
|   |   |   |   llm_evaluator.py
|   |   |   |   rubric_builder.py
|   |   |   |   score_validator.py
|   |   |   |   __init__.py
|   |   startup/
|   |   |   job_cleanup.py
|   |   |   lifespan.py
|   |   |   system_checks.py
|   |   |   worker_manager.py
|   |   utils/
|   |   |   annotation_utils.py
|   |   |   auth.py
|   |   |   blueprint.py
|   |   |   concurrency.py
|   |   |   file_utils.py
|   |   |   gcp_auth.py
|   |   |   gemini_ocr_service.py
|   |   |   hashing.py
|   |   |   ocr_provider.py
|   |   |   paddle_service.py
|   |   |   serialization.py
|   |   |   validation.py
|   |   |   vision_ocr_service.py
|   |   |   __init__.py
|   scripts/
|   |   dump_annotated_images.py
|   |   dump_question_snippets.py
|   |   generate_score_test.py
|   |   migrate_ai_structured_v1.py
|   |   migrate_large_files_to_gridfs.py
|   |   migrate_submissions_to_gridfs.py
|   |   migrate_submission_images_to_gridfs.py
|   |   ocr_debug.py
|   |   regenerate_annotations_for_submission.py
|   |   scan_section_math.py
|   |   test_college_extraction.py
|   |   test_llm.py
|   static/
|   tests/
|   |   test_alignment_parsing.py
|   |   test_aws_pipeline_v3.py
|   |   test_blueprint_enrichment.py
|   |   test_college_v3.py
|   |   test_exam_aliases.py
|   |   test_exam_db_compatibility.py
|   |   test_exam_imports.py
|   |   test_exam_models.py
|   |   test_pipeline_schemas.py
|   |   test_user_backward_imports.py
|   |   test_user_db_model.py
|   |   test_user_refactor.py
|   |   test_user_schema_integrity.py
|   tmp/
|   |   check_all_recent.py
|   |   check_all_recent_json.py
|   |   check_exam.py
|   |   check_exam_subs.py
|   |   check_failed_packet.py
|   |   check_failed_sub.py
|   |   check_jobs.py
|   |   check_job_sub.py
|   |   check_recent.py
|   |   check_recent_sync.py
|   |   check_state.py
|   |   export_failed_sub.py
|   |   failed_sub_debug.json
|   |   generate_tree.py
|   |   get_sample.py
|   |   get_sample_json.py
|   |   inspect_db.py
|   |   inspect_out.txt
|   |   latest_sub.json
|   |   list_exams.py
|   |   recent_subs.json
|   |   recent_subs_output.txt
|   |   tree_output.txt
```
