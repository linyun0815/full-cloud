package cn.full.cloud.module.pms.dal.mysql.kb.content;

import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.pms.dal.dataobject.kb.content.PmsKnowledgeContentPermissionDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.Collection;
import java.util.List;

@Mapper
public interface PmsKnowledgeContentPermissionMapper extends BaseMapperX<PmsKnowledgeContentPermissionDO> {

    default List<PmsKnowledgeContentPermissionDO> selectListByLibraryIds(Collection<Long> libraryIds) {
        return selectList(new LambdaQueryWrapperX<PmsKnowledgeContentPermissionDO>()
                .in(PmsKnowledgeContentPermissionDO::getLibraryId, libraryIds));
    }

    default List<PmsKnowledgeContentPermissionDO> selectListByLibraryId(Long libraryId) {
        return selectList(PmsKnowledgeContentPermissionDO::getLibraryId, libraryId);
    }

}
